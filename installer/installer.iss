; ASA Log Agent — single Setup.exe (Inno Setup).
; Bundles the agent + calibration exe + a pinned Tesseract-OCR installer,
; installs Tesseract visibly (user-approved), asks for token + server label +
; ingest URL, and writes agent.ini to %LOCALAPPDATA%\ASALogAgent. Compiled in CI.
;
; AppVersion is passed by the workflow:  iscc /DAppVersion=v0.1.x installer.iss

#ifndef AppVersion
  #define AppVersion "dev"
#endif

[Setup]
AppName=ASA Log Agent
AppVersion={#AppVersion}
AppPublisher=SinanCakar
; Per-user writable location so config/queue can live in the SAME folder as the
; .exe (Program Files would block runtime writes). User can change it at install.
DefaultDirName={localappdata}\Programs\ASA Log Agent
DefaultGroupName=ASA Log Agent
OutputDir=output
OutputBaseFilename=ASA_LogAgent_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes

[Files]
Source: "..\dist\ASA_LogAgent.exe";           DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\ASA_LogAgent_Calibrate.exe";  DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.txt";                       DestDir: "{app}"; Flags: ignoreversion
; Pinned Tesseract installer, downloaded into vendor\ by the workflow.
Source: "vendor\tesseract-setup.exe";          DestDir: "{tmp}"; Flags: deleteafterinstall

[Tasks]
Name: "installtess"; Description: "Tesseract-OCR 5.3.3 (OCR motoru) kur - gerekli"; GroupDescription: "Bilesenler:"
Name: "desktopicon"; Description: "Masaustu kisayolu olustur"; GroupDescription: "Kisayollar:"; Flags: unchecked

[Icons]
Name: "{group}\ASA Log Agent";              Filename: "{app}\ASA_LogAgent.exe"
Name: "{group}\ASA Log Agent (Kalibrasyon)"; Filename: "{app}\ASA_LogAgent_Calibrate.exe"
Name: "{group}\Kaldir";                      Filename: "{uninstallexe}"
Name: "{autodesktop}\ASA Log Agent";        Filename: "{app}\ASA_LogAgent.exe"; Tasks: desktopicon

[Run]
; Tesseract NSIS installer run VISIBLY so the user sees and approves exactly what
; is installed. /D sets the default dir (must be last, unquoted); no /S = shows UI.
Filename: "{tmp}\tesseract-setup.exe"; Parameters: "/D=C:\Program Files\Tesseract-OCR"; \
  StatusMsg: "Tesseract-OCR kurulum penceresi aciliyor (devam icin onayla)..."; \
  Flags: waituntilterminated; Tasks: installtess
; Offer to run calibration right after install (game should be open).
Filename: "{app}\ASA_LogAgent_Calibrate.exe"; Description: "Simdi ekran bolgesini kalibre et"; \
  Flags: postinstall skipifsilent nowait

[Code]
var
  CfgPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  CfgPage := CreateInputQueryPage(wpSelectDir,
    'ASA Log Agent ayarlari',
    'Bot baglanti bilgileri',
    'Discord''ta  /log key  ile aldigin token''i, oynadigin sunucu adini ve ' +
    'botunun ingest adresini gir. Bunlar agent.ini''ye otomatik yazilacak.');
  CfgPage.Add('Ingest token (/log key):', False);
  CfgPage.Add('Sunucu etiketi (orn: the_island 7777):', False);
  CfgPage.Add('Bot ingest URL (HTTPS):', False);
  CfgPage.Values[2] := 'https://ingest.machinebot.tr/ingest/logs';
end;

function GetIngestUrl: String;
begin
  Result := Trim(CfgPage.Values[2]);
  if Result = '' then
    Result := 'https://ingest.machinebot.tr/ingest/logs';
end;

function ExistingConfig: String;
begin
  // agent.ini already present in the chosen dir => this is an upgrade.
  Result := AddBackslash(WizardDirValue) + 'agent.ini';
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  // On upgrade, keep the existing token/config: skip the credentials page.
  Result := (PageID = CfgPage.ID) and FileExists(ExistingConfig);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = CfgPage.ID then
  begin
    if Trim(CfgPage.Values[0]) = '' then
    begin
      MsgBox('Token bos olamaz. Discord''ta /log key calistirip token al.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure WriteAgentIni;
var
  ini, content: String;
begin
  // Single folder: agent.ini lives next to the .exe (install dir is writable).
  ini := ExpandConstant('{app}\agent.ini');
  if FileExists(ini) then
    exit;  // upgrade: preserve the user's existing token/region/settings
  content :=
    '[agent]' + #13#10 +
    'api_url = ' + GetIngestUrl + #13#10 +
    'token = ' + Trim(CfgPage.Values[0]) + #13#10 +
    'server_label = ' + Trim(CfgPage.Values[1]) + #13#10 +
    'interval = 3' + #13#10 +
    '; region: ASA_LogAgent_Calibrate ile doldurulur (x,y,genislik,yukseklik)' + #13#10 +
    'region = ' + #13#10 +
    'fuzzy_threshold = 0.72' + #13#10 +
    'tesseract_path = C:\Program Files\Tesseract-OCR\tesseract.exe' + #13#10 +
    'queue_file = offline_queue.jsonl' + #13#10 +
    'dedup_window = 200' + #13#10;
  SaveStringToFile(ini, content, False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    WriteAgentIni;
end;

// --- Uninstall: clean up the data dir and optionally remove Tesseract ---
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  appDir, tessUninst: String;
  rc: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    // Settings + local data live next to the exe (single-folder install).
    appDir := ExpandConstant('{app}');
    if MsgBox('Ayarlarini ve verilerini de sil? (agent.ini + token, kuyruk, ekran goruntusu)',
              mbConfirmation, MB_YESNO) = IDYES then
    begin
      DeleteFile(appDir + '\agent.ini');
      DeleteFile(appDir + '\offline_queue.jsonl');
      DeleteFile(appDir + '\calibration_screenshot.png');
    end;
    // Older versions stored data here; clean it up too if present.
    if DirExists(ExpandConstant('{localappdata}\ASALogAgent')) then
      DelTree(ExpandConstant('{localappdata}\ASALogAgent'), True, True, True);

    // Tesseract was installed by its own installer, so remove it separately.
    tessUninst := 'C:\Program Files\Tesseract-OCR\uninstall.exe';
    if FileExists(tessUninst) then
      if MsgBox('Tesseract-OCR da kaldirilsin mi? (baska program kullanmiyorsa Evet)',
                mbConfirmation, MB_YESNO) = IDYES then
        Exec(tessUninst, '', '', SW_SHOW, ewWaitUntilTerminated, rc);
  end;
end;
