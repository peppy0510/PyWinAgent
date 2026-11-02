; http://www.jrsoftware.org/ishelp/index.php

[Setup]
AppName="PyWinAgent"
AppVerName="PyWinAgent 0.1.0"
DefaultDirName="{autopf}\PyWinAgent"
DefaultGroupName="PyWinAgent"
AppVersion="0.1.0"
AppCopyright="Taehong Kim"
AppPublisher="Taehong Kim"
UninstallDisplayIcon="{app}\PyWinAgent.exe"
Compression=lzma2/max
SolidCompression=yes
OutputDir=".dist"
OutputBaseFilename="PyWinAgent-0.1.0-Setup"
; VersionInfoVersion="0.1.0"
VersionInfoProductVersion="0.1.0"
VersionInfoCompany="Taehong Kim"
VersionInfoCopyright="Taehong Kim"
ArchitecturesInstallIn64BitMode="x64compatible"
CloseApplications=yes
RestartApplications=no

[Files]
Source: ".dist\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\PyWinAgent"; Filename: "{app}\PyWinAgent.exe"
Name: "{commondesktop}\PyWinAgent"; Filename: "{app}\PyWinAgent.exe"

[Run]
Filename: "{app}\PyWinAgent.exe"; Description: "Launch PyWinAgent"; Flags: nowait postinstall skipifsilent
