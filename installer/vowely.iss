; Build only the staged, audited runtime. Personal profiles are never sources.
#ifndef Stage
  #error Stage must point to a reviewed installer staging directory
#endif
#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef Output
  #error Output directory is required
#endif
[Setup]
AppId={{A514CF3E-F088-4EA4-91AB-67045C578AFE}
AppName=Vowely
AppVersion={#AppVersion}
AppPublisher=Vowely contributors
AppPublisherURL=https://github.com/DaksheshGautam/vowely
AppSupportURL=https://github.com/DaksheshGautam/vowely/issues
DefaultDirName={localappdata}\Programs\Vowely
DefaultGroupName=Vowely
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
UninstallDisplayIcon={app}\Vowely.exe
SetupIconFile={#Stage}\vowely.ico
WizardStyle=modern dark
Compression=lzma2/fast
SolidCompression=yes
OutputDir={#Output}
OutputBaseFilename=Vowely-{#AppVersion}-Setup-x64
VersionInfoVersion=0.1.0.12
AppMutex=Local\Vowely-Installed
CloseApplications=no
RestartApplications=no
Uninstallable=yes
InfoBeforeFile={#Stage}\INSTALL-NOTES.txt

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "{#Stage}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Vowely\Vowely"; Filename: "{app}\Vowely.exe"; WorkingDir: "{app}"
Name: "{userprograms}\Vowely\Finish Vowely setup"; Filename: "{app}\Vowely.exe"; Parameters: "--setup-wizard"; WorkingDir: "{app}"
Name: "{userprograms}\Vowely\Uninstall Vowely"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Vowely"; Filename: "{app}\Vowely.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Vowely.exe"; Parameters: "--setup-wizard"; Description: "Set up local models and engines"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; Models/settings live outside {app} and are deliberately preserved.
Type: dirifempty; Name: "{app}"
