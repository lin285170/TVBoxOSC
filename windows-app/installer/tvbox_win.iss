; Inno Setup script for TVBoxOSC for Windows
; Compiled on GitHub Actions (windows-latest) or locally with ISCC.exe.
;
; Usage:
;   iscc /DMyAppVersion=1.0.0 installer\tvbox_win.iss
; The PyInstaller onedir output must exist at ..\dist\TVBoxOSC first.
;
; If ChineseSimplified.isl sits next to this script, the wizard gains a
; Simplified Chinese page; otherwise it falls back to English only.

#ifndef MyAppVersion
#define MyAppVersion "0.0.0-dev"
#endif

#define MyAppName "TVBoxOSC"
#define MyAppPublisher "TVBoxOSC"
#define MyAppExeName "TVBoxOSC.exe"
#define MyAppUrl "https://github.com/lin285170/TVBoxOSC"

[Setup]
AppId={{D4A7E1F2-9B3C-4E5A-8F60-1C2D3E4F5A6B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppUrl}
AppSupportURL={#MyAppUrl}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename=TVBoxOSC_Setup_{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=app.ico
ArchitecturesAllowed=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
#if FileExists("ChineseSimplified.isl")
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\TVBoxOSC\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
    Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '')}}"; \
    Flags: nowait postinstall skipifsilent

