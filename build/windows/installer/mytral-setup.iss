; MyTraL Windows Installer (Inno Setup 6)
;
; Usage:
;   ISCC.exe /DMytralAppVersion=1.54.0 mytral-setup.iss
;   or run: build\windows\build-win-installer.bat  (reads version automatically)
;
; Prerequisites:
;   - Build the desktop executable first: make distro-desktop-build-win
;   - Inno Setup 6: https://jrsoftware.org/isinfo.php

#ifndef MytralAppVersion
  #define MytralAppVersion "1.54.0"
#endif

#define MytralAppName "MyTraL"
#define MytralAppPublisher "Martin Dvorak"
#define MytralAppURL "https://mytral.fitness"
#define MytralExeName "mytral.exe"

[Setup]
; AppId uniquely identifies this application — do not reuse in other installers.
AppId={{C3D7F241-8B5E-4A29-9F6D-E1B02A4C7853}
AppName={#MytralAppName}
AppVersion={#MytralAppVersion}
AppPublisher={#MytralAppPublisher}
AppPublisherURL={#MytralAppURL}
AppSupportURL={#MytralAppURL}
AppUpdatesURL={#MytralAppURL}
DefaultDirName={autopf}\{#MytralAppName}
DefaultGroupName={#MytralAppName}
LicenseFile=..\..\..\LICENSE
OutputDir=..\..\..\distro\windows
OutputBaseFilename=mytral-{#MytralAppVersion}-setup
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\{#MytralExeName}
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; PyInstaller single-file executable — all Python dependencies are bundled inside.
Source: "..\..\..\distro\desktop\mytral-{#MytralAppVersion}.exe"; DestDir: "{app}"; DestName: "{#MytralExeName}"; Flags: ignoreversion 64bit

[Icons]
Name: "{group}\{#MytralAppName}"; Filename: "{app}\{#MytralExeName}"
Name: "{commondesktop}\{#MytralAppName}"; Filename: "{app}\{#MytralExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MytralExeName}"; Flags: shellexec nowait postinstall skipifsilent runascurrentuser; Description: "{cm:LaunchProgram,{#StringChange(MytralAppName, '&', '&&')}}"
