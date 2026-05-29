# MyTraL: my trailing log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
import datetime
import os
import threading
import traceback
import uuid

import flask
import structlog

from mytral import app_config
from mytral import app_user_ds as ds
from mytral import forms
from mytral import security
from mytral.ai import acoaches as ai_chats
from mytral.ai import agent as ai_agent
from mytral.ai import providers as ai_providers
from mytral.ai import settings as ai_settings
from mytral.routes import COOKIE_USER
from mytral.routes import flask_app

_logger = structlog.get_logger()


def _avatar_store():
    """Return the global blob store for avatar operations."""
    import mytral

    return mytral.app_blobstore


#
# Background agent execution
#


def _run_agent_in_background(
    user_id: str,
    chat_key: str,
    message_index: int,
    coach: ai_settings.ACoach,
    provider: ai_settings.AiProvider,
    model_name: str,
    encryption_key: str,
    user_profile: object,
    llm_messages: list[dict],
) -> None:
    """Run the PydanticAI agent in a daemon thread and persist the result.

    Parameters
    ----------
    user_id : str
        Authenticated user ID used to locate the chats file.
    chat_key : str
        UUID key of the chat to update.
    message_index : int
        Index of the placeholder assistant message to fill in.
    coach : ai_settings.ACoach
        Coach configuration.
    provider : ai_settings.AiProvider
        LLM provider configuration.
    model_name : str
        Model name string.
    encryption_key : str
        Encryption key for decrypting API secrets.
    user_profile : object
        User profile passed to agent tools.
    llm_messages : list[dict]
        Message history sent to the agent.
    """
    with flask_app.app_context():
        try:
            reply = ai_agent.run_agent(
                coach=coach,
                provider=provider,
                model_name=model_name,
                encryption_key=encryption_key,
                user_profile=user_profile,
                dataset=ds,
                messages=llm_messages,
            )
            new_status = "done"
        except Exception as exc:
            error_type = type(exc).__name__
            error_msg = str(exc)
            # body field is present on UnexpectedModelBehavior / ModelHTTPError
            body = getattr(exc, "body", None)
            tb = traceback.format_exc()
            _logger.error(
                "acoaching: background agent failed",
                coach=coach.name,
                model=model_name,
                error_type=error_type,
                error=error_msg,
                response_body=str(body) if body else None,
                traceback=tb,
            )
            # build user-friendly markdown — raw error goes inside <details> so
            # the user sees a clean message and the developer can see the cause
            tech_detail = error_msg
            if body:
                tech_detail += f"\n\nResponse body:\n```\n{body}\n```"
            reply = (
                "**ACoach did not respond.**\n\n"
                "> *The coach was unable to generate a structured response. "
                "This can happen with smaller or less capable models — "
                "try rephrasing your question, or switch to a more capable model.*\n\n"
                "<details><summary>Technical details</summary>\n\n"
                f"**{error_type}**\n\n"
                f"```\n{tech_detail}\n```\n\n"
                "</details>"
            )
            new_status = "error"

        chats = ai_chats.load_acoach_chats(user_id=user_id, data_dir=str(ds.data_dir))
        chat = next((c for c in chats if c.key == chat_key), None)
        if chat and message_index < len(chat.messages):
            chat.messages[message_index].content = reply
            chat.messages[message_index].status = new_status
            ai_chats.save_acoach_chats(
                user_id=user_id, data_dir=str(ds.data_dir), chats=chats
            )
        else:
            _logger.warning(
                "acoaching: background agent could not find chat to update",
                chat_key=chat_key,
                message_index=message_index,
            )


#
# Settings: ACoach providers, models, coaches
#


@flask_app.route("/app/settings/acoaches", methods=["GET"])
def settings_acoaches():
    """Render ACoach settings page."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)
    ac_settings = user_profile.acoach_settings or ai_settings.ACoachSettings.empty()

    all_types = [
        ("ollama", "Ollama (local, private)"),
        ("anthropic", "Anthropic (WARNING: sends data to 3rd party)"),
        ("openai", "OpenAI (WARNING: sends data to 3rd party)"),
    ]
    existing_types = {p.type for p in ac_settings.providers}
    available_types = [(v, label) for v, label in all_types if v not in existing_types]

    provider_form = forms.AiProviderForm()
    provider_form.type.choices = available_types
    add_model_form = forms.AiModelForm()
    add_model_form.provider_key.choices = [
        (p.key, f"{p.type} @ {p.url or 'default'}") for p in ac_settings.providers
    ]
    model_choices = [("", "— no model —")] + [
        (m.key, m.model_name) for m in ac_settings.models
    ]
    add_coach_form = forms.ACoachForm()
    add_coach_form.model_key.choices = model_choices

    # build a pre-filled edit form for each existing coach
    edit_coach_forms = {}
    for coach in ac_settings.coaches:
        ef = forms.ACoachForm()
        ef.model_key.choices = model_choices
        ef.name.data = coach.name
        ef.model_key.data = coach.model_key
        ef.system_prompt.data = coach.system_prompt
        edit_coach_forms[coach.key] = ef

    # build per-coach avatar forms
    coach_avatar_upload_forms = {}
    coach_avatar_delete_forms = {}
    for coach in ac_settings.coaches:
        coach_avatar_upload_forms[coach.key] = forms.UploadAvatarForm(
            prefix=f"cau-{coach.key}"
        )
        coach_avatar_delete_forms[coach.key] = forms.DeleteAvatarForm(
            prefix=f"cad-{coach.key}"
        )

    models_by_key = {m.key: m for m in ac_settings.models}
    providers_by_key = {p.key: p for p in ac_settings.providers}

    ollama_env_set = bool(os.environ.get(ai_providers.LlmProviderType.ENV_OLLAMA_KEY))
    anthropic_env_set = bool(
        os.environ.get(ai_providers.LlmProviderType.ENV_ANTHROPIC_KEY)
    )
    openai_env_set = bool(os.environ.get(ai_providers.LlmProviderType.ENV_OPENAI_KEY))

    return flask.render_template(
        "settings-acoaches.html",
        user_profile=user_profile,
        ac_settings=ac_settings,
        add_provider_form=provider_form,
        can_add_provider=bool(available_types),
        add_model_form=add_model_form,
        add_coach_form=add_coach_form,
        edit_coach_forms=edit_coach_forms,
        coach_avatar_upload_forms=coach_avatar_upload_forms,
        coach_avatar_delete_forms=coach_avatar_delete_forms,
        models_by_key=models_by_key,
        providers_by_key=providers_by_key,
        ootb_prompts={
            "tony_d": ai_settings.OOTB_TONY_D_PROMPT,
            "bohous": ai_settings.OOTB_BOHOUS_PROMPT,
            "emil": ai_settings.OOTB_EMIL_PROMPT,
        },
        ollama_env_set=ollama_env_set,
        anthropic_env_set=anthropic_env_set,
        openai_env_set=openai_env_set,
    )


@flask_app.route("/app/settings/acoaches/providers/add", methods=["POST"])
def settings_acoaches_provider_add():
    """Add a new AI provider."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)
    ac_settings = user_profile.acoach_settings or ai_settings.ACoachSettings.empty()

    form = forms.AiProviderForm()
    if form.validate_on_submit():
        provider_type = form.type.data
        existing_types = {p.type for p in ac_settings.providers}
        if provider_type in existing_types:
            flask.flash(
                f"A {provider_type} provider already exists. "
                "Remove it first before adding another.",
                "danger",
            )
            return flask.redirect(flask.url_for("settings_acoaches"))

        raw_api_key = form.api_key.data or ""
        api_key_enc = ""
        if raw_api_key:
            api_key_enc = security.encrypt(raw_api_key, app_config.encryption_key)

        provider = ai_settings.AiProvider(
            key=str(uuid.uuid4()),
            type=provider_type,
            url=form.url.data or "",
            api_key_enc=api_key_enc,
            api_key_from_env=bool(form.from_env.data),
        )
        ac_settings.providers.append(provider)
        user_profile.acoach_settings = ac_settings
        ds.update_profile(user_profile)
        flask.flash("Provider added.", "success")

    return flask.redirect(flask.url_for("settings_acoaches"))


@flask_app.route(
    "/app/settings/acoaches/providers/<provider_key>/delete", methods=["POST"]
)
def settings_acoaches_provider_delete(provider_key: str):
    """Delete an AI provider."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)
    ac_settings = user_profile.acoach_settings or ai_settings.ACoachSettings.empty()

    ac_settings.providers = [p for p in ac_settings.providers if p.key != provider_key]
    # remove models that referenced this provider
    ac_settings.models = [
        m for m in ac_settings.models if m.provider_key != provider_key
    ]
    user_profile.acoach_settings = ac_settings
    ds.update_profile(user_profile)
    flask.flash("Provider deleted.", "success")
    return flask.redirect(flask.url_for("settings_acoaches"))


@flask_app.route("/app/settings/acoaches/models/add", methods=["POST"])
def settings_acoaches_model_add():
    """Add a new AI model configuration."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)
    ac_settings = user_profile.acoach_settings or ai_settings.ACoachSettings.empty()

    form = forms.AiModelForm()
    form.provider_key.choices = [
        (p.key, f"{p.type} @ {p.url or 'default'}") for p in ac_settings.providers
    ]
    if form.validate_on_submit():
        model = ai_settings.AiModel(
            key=str(uuid.uuid4()),
            provider_key=form.provider_key.data,
            model_name=form.model_name.data,
        )
        ac_settings.models.append(model)
        user_profile.acoach_settings = ac_settings
        ds.update_profile(user_profile)
        flask.flash("Model added.", "success")

    return flask.redirect(flask.url_for("settings_acoaches"))


@flask_app.route("/app/settings/acoaches/models/<model_key>/delete", methods=["POST"])
def settings_acoaches_model_delete(model_key: str):
    """Delete an AI model configuration."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)
    ac_settings = user_profile.acoach_settings or ai_settings.ACoachSettings.empty()

    ac_settings.models = [m for m in ac_settings.models if m.key != model_key]
    user_profile.acoach_settings = ac_settings
    ds.update_profile(user_profile)
    flask.flash("Model deleted.", "success")
    return flask.redirect(flask.url_for("settings_acoaches"))


@flask_app.route(
    "/app/settings/acoaches/providers/<provider_key>/list-models", methods=["GET"]
)
def settings_acoaches_provider_list_models(provider_key: str):
    """Return available model names for an Ollama provider as JSON."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.jsonify({"error": "Not authenticated"}), 401
    user_profile = ds.profile(user_id)
    ac_settings = user_profile.acoach_settings or ai_settings.ACoachSettings.empty()

    provider = next((p for p in ac_settings.providers if p.key == provider_key), None)
    if not provider:
        return flask.jsonify({"error": "Provider not found"}), 404

    models = ai_providers.list_models(provider, app_config.encryption_key)
    return flask.jsonify({"models": models})


@flask_app.route("/app/settings/acoaches/coaches/add", methods=["POST"])
def settings_acoaches_coach_add():
    """Add a new AI coach persona."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)
    ac_settings = user_profile.acoach_settings or ai_settings.ACoachSettings.empty()

    form = forms.ACoachForm()
    form.model_key.choices = [("", "— no model —")] + [
        (m.key, m.model_name) for m in ac_settings.models
    ]
    if form.validate_on_submit():
        coach = ai_settings.ACoach(
            key=str(uuid.uuid4()),
            name=form.name.data,
            model_key=form.model_key.data or "",
            system_prompt=form.system_prompt.data,
        )
        ac_settings.coaches.append(coach)
        user_profile.acoach_settings = ac_settings
        ds.update_profile(user_profile)
        flask.flash("Coach added.", "success")

    return flask.redirect(flask.url_for("settings_acoaches"))


@flask_app.route("/app/settings/acoaches/coaches/<coach_key>/delete", methods=["POST"])
def settings_acoaches_coach_delete(coach_key: str):
    """Delete an AI coach persona."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)
    ac_settings = user_profile.acoach_settings or ai_settings.ACoachSettings.empty()

    # delete avatar blob before removing the coach to avoid orphans
    from mytral import blobstore as blob_pkg

    for coach in ac_settings.coaches:
        if coach.key == coach_key and coach.photo_blob_key:
            try:
                svc = blob_pkg.AvatarBlobService(store=_avatar_store())
                svc.delete_avatar(user_id=user_id, blob_key=coach.photo_blob_key)
            except Exception:
                pass  # best-effort

    ac_settings.coaches = [c for c in ac_settings.coaches if c.key != coach_key]
    user_profile.acoach_settings = ac_settings
    ds.update_profile(user_profile)
    flask.flash("Coach deleted.", "success")
    return flask.redirect(flask.url_for("settings_acoaches"))


@flask_app.route(
    "/app/settings/acoaches/coaches/<coach_key>/avatar/upload", methods=["POST"]
)
def settings_acoaches_coach_avatar_upload(coach_key: str):
    """Upload and replace the avatar photo for an AI coach."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    form = forms.UploadAvatarForm(prefix=f"cau-{coach_key}")
    if not form.validate_on_submit():
        flask.flash(message="Avatar upload form validation failed.", category="error")
        return flask.redirect(flask.url_for("settings_acoaches"))

    user_profile = ds.profile(user_id)
    ac_settings = user_profile.acoach_settings or ai_settings.ACoachSettings.empty()
    coach = next((c for c in ac_settings.coaches if c.key == coach_key), None)
    if coach is None:
        flask.flash(message="Coach not found.", category="error")
        return flask.redirect(flask.url_for("settings_acoaches"))

    f = form.photo.data
    raw = f.stream.read()
    ext = "." + (f.filename.rsplit(".", 1)[-1] if "." in f.filename else "jpg")

    from mytral import blobstore as blob_pkg

    svc = blob_pkg.AvatarBlobService(store=_avatar_store())
    old_blob_key = coach.photo_blob_key
    try:
        meta = svc.upload_coach_avatar(
            user_id=user_id, coach_key=coach_key, data=raw, extension=ext
        )
    except (blob_pkg.BlobValidationError, blob_pkg.BlobStoreError) as exc:
        _logger.exception(
            "avatar.upload_coach_failed",
            user_id=user_id,
            coach_key=coach_key,
            exc=str(exc),
        )
        flask.flash(message=f"Avatar upload failed: {exc}", category="error")
        return flask.redirect(flask.url_for("settings_acoaches"))

    coach.photo_blob_key = meta.blob_key
    user_profile.acoach_settings = ac_settings
    ds.update_profile(user_profile)

    if old_blob_key:
        try:
            svc.delete_avatar(user_id=user_id, blob_key=old_blob_key)
        except Exception:
            pass  # best-effort

    flask.flash(message="Coach avatar updated.", category="success")
    return flask.redirect(flask.url_for("settings_acoaches"))


@flask_app.route(
    "/app/settings/acoaches/coaches/<coach_key>/avatar/delete", methods=["POST"]
)
def settings_acoaches_coach_avatar_delete(coach_key: str):
    """Remove the avatar photo for an AI coach."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    form = forms.DeleteAvatarForm(prefix=f"cad-{coach_key}")
    if not form.validate_on_submit():
        flask.flash(message="Delete avatar form validation failed.", category="error")
        return flask.redirect(flask.url_for("settings_acoaches"))

    user_profile = ds.profile(user_id)
    ac_settings = user_profile.acoach_settings or ai_settings.ACoachSettings.empty()
    coach = next((c for c in ac_settings.coaches if c.key == coach_key), None)
    if coach is None:
        flask.flash(message="Coach not found.", category="error")
        return flask.redirect(flask.url_for("settings_acoaches"))

    blob_key = coach.photo_blob_key
    if blob_key:
        from mytral import blobstore as blob_pkg

        svc = blob_pkg.AvatarBlobService(store=_avatar_store())
        coach.photo_blob_key = ""
        user_profile.acoach_settings = ac_settings
        ds.update_profile(user_profile)
        try:
            svc.delete_avatar(user_id=user_id, blob_key=blob_key)
        except Exception:
            pass  # best-effort

    flask.flash(message="Coach avatar removed.", category="success")
    return flask.redirect(flask.url_for("settings_acoaches"))


@flask_app.route("/app/settings/acoaches/coaches/<coach_key>/avatar", methods=["GET"])
def settings_acoaches_coach_avatar(coach_key: str):
    """Serve the coach's full-size (200×200) avatar JPEG."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        flask.abort(404)

    user_profile = ds.profile(user_id)
    ac_settings = user_profile.acoach_settings or ai_settings.ACoachSettings.empty()
    coach = next((c for c in ac_settings.coaches if c.key == coach_key), None)
    if coach is None or not coach.photo_blob_key:
        flask.abort(404)

    from mytral import blobstore as blob_pkg

    svc = blob_pkg.AvatarBlobService(store=_avatar_store())
    try:
        stream = svc.open_coach_avatar(user_id=user_id, blob_key=coach.photo_blob_key)
        return flask.send_file(stream, mimetype="image/jpeg")
    except blob_pkg.BlobNotFoundError:
        flask.abort(404)


@flask_app.route(
    "/app/settings/acoaches/coaches/<coach_key>/avatar/thumbnail", methods=["GET"]
)
def settings_acoaches_coach_avatar_thumbnail(coach_key: str):
    """Serve the coach's 40×40 avatar thumbnail JPEG."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        flask.abort(404)

    user_profile = ds.profile(user_id)
    ac_settings = user_profile.acoach_settings or ai_settings.ACoachSettings.empty()
    coach = next((c for c in ac_settings.coaches if c.key == coach_key), None)
    if coach is None or not coach.photo_blob_key:
        flask.abort(404)

    from mytral import blobstore as blob_pkg

    svc = blob_pkg.AvatarBlobService(store=_avatar_store())
    try:
        stream = svc.open_coach_avatar(
            user_id=user_id, blob_key=coach.photo_blob_key, thumbnail=True
        )
        return flask.send_file(stream, mimetype="image/jpeg")
    except blob_pkg.BlobNotFoundError:
        flask.abort(404)


@flask_app.route("/app/settings/acoaches/coaches/<coach_key>/update", methods=["POST"])
def settings_acoaches_coach_update(coach_key: str):
    """Update an existing AI coach persona."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)
    ac_settings = user_profile.acoach_settings or ai_settings.ACoachSettings.empty()

    form = forms.ACoachForm()
    form.model_key.choices = [("", "— no model —")] + [
        (m.key, m.model_name) for m in ac_settings.models
    ]
    if form.validate_on_submit():
        for coach in ac_settings.coaches:
            if coach.key == coach_key:
                coach.name = form.name.data
                coach.model_key = form.model_key.data or ""
                coach.system_prompt = form.system_prompt.data
                break
        user_profile.acoach_settings = ac_settings
        ds.update_profile(user_profile)
        flask.flash("Coach updated.", "success")
    else:
        flask.flash("Could not save coach — check the form.", "danger")

    return flask.redirect(flask.url_for("settings_acoaches"))


#
# ACoaching chat
#


@flask_app.route("/app/acoaching", methods=["GET"])
def acoaching():
    """Render the main AI coaching page with chat history."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)
    ac_settings = user_profile.acoach_settings or ai_settings.ACoachSettings.empty()

    chats = ai_chats.load_acoach_chats(
        user_id=user_profile.user_id, data_dir=str(ds.data_dir)
    )

    # only expose coaches that have a model assigned
    ready_coaches = [c for c in ac_settings.coaches if c.model_key]

    message_form = forms.ACoachMessageForm()
    message_form.coach_key.choices = [("", "— select coach —")] + [
        (c.key, c.name) for c in ready_coaches
    ]

    return flask.render_template(
        "acoaching.html",
        user_profile=user_profile,
        ac_settings=ac_settings,
        chats=chats,
        active_chat=None,
        message_form=message_form,
        ready_coaches=ready_coaches,
    )


@flask_app.route("/app/acoaching/chat/<chat_key>", methods=["GET"])
def acoaching_chat(chat_key: str):
    """View a specific coaching chat thread."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)
    ac_settings = user_profile.acoach_settings or ai_settings.ACoachSettings.empty()

    chats = ai_chats.load_acoach_chats(
        user_id=user_profile.user_id, data_dir=str(ds.data_dir)
    )
    active_chat = next((c for c in chats if c.key == chat_key), None)

    # only expose coaches that have a model assigned
    ready_coaches = [c for c in ac_settings.coaches if c.model_key]

    message_form = forms.ACoachMessageForm()
    message_form.coach_key.choices = [("", "— select coach —")] + [
        (c.key, c.name) for c in ready_coaches
    ]

    return flask.render_template(
        "acoaching.html",
        user_profile=user_profile,
        ac_settings=ac_settings,
        chats=chats,
        active_chat=active_chat,
        message_form=message_form,
        ready_coaches=ready_coaches,
    )


@flask_app.route("/app/acoaching/chat/new", methods=["POST"])
def acoaching_chat_new():
    """Create a new chat; run the AI agent in a background thread."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)
    ac_settings = user_profile.acoach_settings or ai_settings.ACoachSettings.empty()

    coach_key = flask.request.form.get("coach_key", "")
    coach = next((c for c in ac_settings.coaches if c.key == coach_key), None)
    if not coach:
        flask.flash("Please select a coach.", "warning")
        return flask.redirect(flask.url_for("acoaching"))

    model = next((m for m in ac_settings.models if m.key == coach.model_key), None)
    if not model:
        flask.flash(
            "Coach has no model configured. Set one in ACoach settings.", "warning"
        )
        return flask.redirect(flask.url_for("settings_acoaches"))

    provider = next(
        (p for p in ac_settings.providers if p.key == model.provider_key), None
    )
    if not provider:
        flask.flash("Model provider not found. Check ACoach settings.", "warning")
        return flask.redirect(flask.url_for("settings_acoaches"))

    user_message = flask.request.form.get("content", "").strip()
    if not user_message:
        flask.flash("Please enter a message.", "warning")
        return flask.redirect(flask.url_for("acoaching"))

    ts_now = datetime.datetime.now().isoformat()
    chat_key = str(uuid.uuid4())
    llm_messages = [{"role": "user", "content": user_message}]

    # placeholder assistant message — agent fills it in via background thread
    chat = ai_chats.ACoachChat(
        key=chat_key,
        coach_key=coach_key,
        title=user_message[:60],
        created_at=ts_now,
        messages=[
            ai_chats.ACoachMessage(role="user", content=user_message, ts=ts_now),
            ai_chats.ACoachMessage(
                role="assistant", content="", ts=ts_now, status="pending"
            ),
        ],
    )

    chats = ai_chats.load_acoach_chats(
        user_id=user_profile.user_id, data_dir=str(ds.data_dir)
    )
    chats.insert(0, chat)
    ai_chats.save_acoach_chats(
        user_id=user_profile.user_id, data_dir=str(ds.data_dir), chats=chats
    )

    threading.Thread(
        target=_run_agent_in_background,
        args=(
            user_profile.user_id,
            chat_key,
            1,  # index of the placeholder assistant message
            coach,
            provider,
            model.model_name,
            app_config.encryption_key,
            user_profile,
            llm_messages,
        ),
        daemon=True,
    ).start()

    return flask.redirect(flask.url_for("acoaching_chat", chat_key=chat_key))


@flask_app.route("/app/acoaching/chat/<chat_key>/message", methods=["POST"])
def acoaching_chat_message(chat_key: str):
    """Send a follow-up message; run the AI agent in a background thread."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)
    ac_settings = user_profile.acoach_settings or ai_settings.ACoachSettings.empty()

    chats = ai_chats.load_acoach_chats(
        user_id=user_profile.user_id, data_dir=str(ds.data_dir)
    )
    chat = next((c for c in chats if c.key == chat_key), None)
    if not chat:
        flask.flash("Chat not found.", "danger")
        return flask.redirect(flask.url_for("acoaching"))

    # block sending while a reply is already pending
    if any(m.status == "pending" for m in chat.messages):
        flask.flash("Please wait for the coach to finish responding.", "warning")
        return flask.redirect(flask.url_for("acoaching_chat", chat_key=chat_key))

    coach = next((c for c in ac_settings.coaches if c.key == chat.coach_key), None)
    if not coach:
        flask.flash("Coach not found for this chat.", "warning")
        return flask.redirect(flask.url_for("acoaching"))

    model = next((m for m in ac_settings.models if m.key == coach.model_key), None)
    if not model:
        flask.flash("Coach has no model configured.", "warning")
        return flask.redirect(flask.url_for("settings_acoaches"))

    provider = next(
        (p for p in ac_settings.providers if p.key == model.provider_key), None
    )
    if not provider:
        flask.flash("Model provider not found.", "warning")
        return flask.redirect(flask.url_for("settings_acoaches"))

    user_message = flask.request.form.get("content", "").strip()
    if not user_message:
        flask.flash("Please enter a message.", "warning")
        return flask.redirect(flask.url_for("acoaching_chat", chat_key=chat_key))

    ts_now = datetime.datetime.now().isoformat()

    # build full message history for the agent
    llm_messages = [{"role": m.role, "content": m.content} for m in chat.messages]
    llm_messages.append({"role": "user", "content": user_message})

    # append user message + pending placeholder, then save before spawning thread
    chat.messages.append(
        ai_chats.ACoachMessage(role="user", content=user_message, ts=ts_now)
    )
    placeholder_index = len(chat.messages)
    chat.messages.append(
        ai_chats.ACoachMessage(
            role="assistant", content="", ts=ts_now, status="pending"
        )
    )
    ai_chats.save_acoach_chats(
        user_id=user_profile.user_id, data_dir=str(ds.data_dir), chats=chats
    )

    threading.Thread(
        target=_run_agent_in_background,
        args=(
            user_profile.user_id,
            chat_key,
            placeholder_index,
            coach,
            provider,
            model.model_name,
            app_config.encryption_key,
            user_profile,
            llm_messages,
        ),
        daemon=True,
    ).start()

    return flask.redirect(flask.url_for("acoaching_chat", chat_key=chat_key))


@flask_app.route("/app/acoaching/chat/<chat_key>/poll", methods=["GET"])
def acoaching_chat_poll(chat_key: str):
    """Return current chat messages as JSON for FE polling.

    Returns
    -------
    flask.Response
        JSON with ``pending`` bool and ``messages`` list.
    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.jsonify({"error": "unauthorized"}), 401

    user_profile = ds.profile(user_id)
    chats = ai_chats.load_acoach_chats(
        user_id=user_profile.user_id, data_dir=str(ds.data_dir)
    )
    chat = next((c for c in chats if c.key == chat_key), None)
    if not chat:
        return flask.jsonify({"error": "not found"}), 404

    pending = any(m.status == "pending" for m in chat.messages)
    messages = [
        {"role": m.role, "content": m.content, "status": m.status, "ts": m.ts}
        for m in chat.messages
    ]
    return flask.jsonify({"pending": pending, "messages": messages})


@flask_app.route("/app/acoaching/chat/<chat_key>/delete", methods=["POST"])
def acoaching_chat_delete(chat_key: str):
    """Delete a coaching chat."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    chats = ai_chats.load_acoach_chats(
        user_id=user_profile.user_id, data_dir=str(ds.data_dir)
    )
    chats = [c for c in chats if c.key != chat_key]
    ai_chats.save_acoach_chats(
        user_id=user_profile.user_id, data_dir=str(ds.data_dir), chats=chats
    )
    flask.flash("Chat deleted.", "success")
    return flask.redirect(flask.url_for("acoaching"))
