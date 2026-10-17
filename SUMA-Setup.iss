; SUMA Installer Script — compile with Inno Setup (https://jrsoftware.org/isdl.php)
; Place this file in D:\SUMA\ and make sure dist\SUMA.exe exists first.
#define MyAppName "SUMA"
#define MyAppVersion "2.0"
#define MyAppPublisher "MRS KRYPTON"
#define MyAppExeName "SUMA.exe"

[Setup]
AppId={{d6b87c64-f233-4aa1-97e2-36066ee6ce7b}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\SUMA
DefaultGroupName=SUMA
OutputDir=.
OutputBaseFilename=SUMA-Setup
SetupIconFile=assets\suma-icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
