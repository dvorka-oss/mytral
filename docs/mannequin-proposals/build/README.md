# Mannequin geometry build

The realistic muscle geometry in the proposal HTML files is generated from the
**MIT-licensed** [react-native-body-highlighter](https://github.com/HichamELBSI/react-native-body-highlighter)
muscle path data.

## Files
- `bodyFront.ts`, `bodyBack.ts`, `wrapper.tsx` — vendored upstream source (muscle
  paths + body outline), © 2022 ELABBASSI Hicham, MIT (see `UPSTREAM-LICENSE-MIT`).
- `build.py` — parses the `.ts` files into per-muscle SVG `<path>` fragments
  (`front.frag`, `back.frag`) + the body outline (`outline.json`), re-tagging each
  path with MyTraL's `data-muscle-key` / `data-part-id`.
- `gen.py` — assembles the three proposal HTML pages from those fragments.

## Regenerate
```bash
python3 build.py   # -> front.frag, back.frag, outline.json
python3 gen.py     # -> ../proposal-{1,2,3}-*.html
```

## Slug → muscle_groups.py key mapping
chest→pecs, deltoids→shoulders, biceps→biceps, triceps→triceps, forearm→forearms,
abs→abs, obliques→obliques, trapezius→traps, upper-back→lats, lower-back→lower_back,
gluteal→glutes, quadriceps→quads, hamstring→hamstrings, calves+tibialis→calves,
neck→neck, adductors→hip_flexors. head/hair/hands/feet→silhouette; knees/ankles→joints.

## License note (AGPL-safe)
MIT is compatible with MyTraL's AGPL-3.0. Retain the upstream MIT copyright notice
when the paths are moved into `mytral/templates/macros/mannequin.html`.
