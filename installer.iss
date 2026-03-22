; installer.iss
; =============
; Inno Setup 6 script for the EI Fragment Exact-Mass Calculator.
;
; Prerequisites
;   1. Run PyInstaller first:
;        pyinstaller ei_fragment_gui.spec --noconfirm
;   2. Then compile this script:
;        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
;
; The finished installer is written to:
;        installer_output\EI-Fragment-Calculator-v1.6.3-Setup.exe

; ---------------------------------------------------------------------------
; Version — update when releasing a new version
; ---------------------------------------------------------------------------
#define AppVersion    "1.6.3"
#define AppName       "EI Fragment Exact-Mass Calculator"
#define AppPublisher  "joriener"
#define AppURL        "https://github.com/joriener/ei-fragment-calculator"
#define AppExeName    "ei-fragment-gui.exe"
#define DistDir       "dist\ei-fragment-gui"

[Setup]
AppId={{B7A2E4F1-3C9D-4E8A-B561-D02F1A7C3E9B}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} v{#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases

; Installation directory
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes

; Output
OutputDir=installer_output
OutputBaseFilename=EI-Fragment-Calculator-v{#AppVersion}-Setup
SetupIconFile=docs\icon.ico
; ^ Remove the line above if you don't have docs\icon.ico

; Compression
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; Require 64-bit Windows 10 or later
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
MinVersion=10.0

; Misc
WizardStyle=modern
DisableProgramGroupPage=no
; Show the license before the user can install
LicenseFile=LICENSE
; Show the README after installation
InfoAfterFile=README.md
; Allow uninstall from Add/Remove Programs
Uninstallable=yes
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
CreateUninstallRegKey=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german";  MessagesFile: "compiler:Languages\German.isl"

[Tasks]
; Desktop shortcut is ticked by default
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; The entire PyInstaller output directory
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu
Name: "{group}\{#AppName}";             Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#AppName}";   Filename: "{uninstallexe}"

; Desktop (created only when the task is ticked)
Name: "{autodesktop}\{#AppName}";       Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; Offer to launch the app at the end of the wizard
Filename: "{app}\{#AppExeName}"; \
    Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; \
    Flags: nowait postinstall skipifsilent

[Registry]
; Register the application so Windows can find it
Root: HKLM; Subkey: "Software\{#AppPublisher}\{#AppName}"; \
    ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; \
    Flags: uninsdeletekey

[UninstallDelete]
; Clean up settings file left by the app in the user's home directory
; (only removes the file if the user agrees during uninstall — handled by
;  the uninstaller's built-in prompt)
Type: files; Name: "{userdocs}\.ei_fragment_calculator_gui.json"
