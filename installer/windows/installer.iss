; Inno Setup Script for SinoPac AutoReply
; Requires Inno Setup 6.x

#define MyAppName "SinoPac AutoReply"
#define MyAppNameZH "永豐金證券 社群自動回覆系統"
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppPublisher "SinoPac Securities"
#define MyAppExeName "SinoPacAutoReply.exe"

[Setup]
AppId={{B8A3E2F1-7C4D-4E5A-9F6B-1A2B3C4D5E6F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\..\dist
OutputBaseFilename=SinoPacAutoReply-Setup-{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppNameZH}
; Uncomment below if you have an icon file
; SetupIconFile=..\..\assets\icons\icon.ico

[Languages]
Name: "tchinese"; MessagesFile: "compiler:Languages\ChineseTraditional.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "建立桌面捷徑(&D)"; GroupDescription: "附加圖示:"; Flags: unchecked

[Files]
; Copy the entire PyInstaller output folder
Source: "..\..\dist\SinoPacAutoReply\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppNameZH}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\解除安裝 {#MyAppNameZH}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppNameZH}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即啟動 {#MyAppNameZH}"; Flags: nowait postinstall skipifsilent
