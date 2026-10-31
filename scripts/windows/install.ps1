# 포트폴리오 봇 설치 · 업데이트 · 재시작 (install.bat 이 실행합니다)
#  1) 이 폴더의 파일을 C:\portfolio-bot 으로 복사 (.env, .venv, data 는 보존)
#  2) Python 가상환경과 패키지 설치
#  3) 봇 토큰 입력·확인 (텔레그램 연결 시험 포함)
#  4) 로그인 시 자동 시작 등록 후 백그라운드 실행
#  5) 처음이면 휴대폰에서 [시작]을 누를 때까지 기다렸다가 등록 완료 안내

$ErrorActionPreference = 'Continue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Dest = 'C:\portfolio-bot'
$Src = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path.TrimEnd('\')
$EnvPath = Join-Path $Dest '.env'
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false

function Say([string]$Text, [string]$Color = 'Gray') { Write-Host $Text -ForegroundColor $Color }
function Fail([string]$Text) {
    Say ''
    Say "[실패] $Text" Red
    exit 1
}

function Get-EnvValue([string]$Name) {
    if (-not (Test-Path $EnvPath)) { return '' }
    $text = [IO.File]::ReadAllText($EnvPath)
    $m = [regex]::Match($text, "(?m)^$Name=([^\r\n]*)")
    if ($m.Success) { return $m.Groups[1].Value.Trim() }
    return ''
}

function Set-EnvValue([string]$Name, [string]$Value) {
    $text = [IO.File]::ReadAllText($EnvPath)
    if ([regex]::IsMatch($text, "(?m)^$Name=")) {
        $text = [regex]::Replace($text, "(?m)^$Name=[^\r\n]*", "$Name=$Value")
    } else {
        $text = $text.TrimEnd() + "`r`n$Name=$Value`r`n"
    }
    [IO.File]::WriteAllText($EnvPath, $text, $Utf8NoBom)
}

function Stop-Bot {
    Get-CimInstance Win32_Process | Where-Object {
        $_.ProcessId -ne $PID -and $_.CommandLine -and (
            $_.CommandLine -like '*start_bot.bat*' -or
            ($_.Name -like 'python*' -and $_.CommandLine -like '*-m bot*'))
    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

# 텔레그램 getMe 로 토큰 확인. 봇 아이디 반환, 토큰이 틀리면 '', 연결 실패면 $null
function Test-Token([string]$Token) {
    try {
        $me = Invoke-RestMethod -Uri "https://api.telegram.org/bot$Token/getMe" -TimeoutSec 30
        return [string]$me.result.username
    } catch {
        $resp = $_.Exception.Response
        if ($resp -and ([int]$resp.StatusCode -in 401, 404)) { return '' }
        return $null
    }
}

Say '=========================================' Cyan
Say '  포트폴리오 알림 봇 설치 / 업데이트' Cyan
Say '=========================================' Cyan

# 1) 실행 중인 봇 중지 후 파일 복사
Say ''
Say '[1/5] 파일 복사 중...'
Stop-Bot
if ($Src -ne $Dest) {
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    robocopy $Src $Dest /E /XD .venv data .git __pycache__ /XF .env /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { Fail "파일 복사에 실패했습니다 (robocopy 코드 $LASTEXITCODE)." }
}
foreach ($old in 'scripts\windows\setup.bat', 'scripts\windows\update.bat', 'scripts\windows\install_autostart.bat') {
    Remove-Item (Join-Path $Dest $old) -Force -ErrorAction SilentlyContinue
}
Get-ChildItem $Dest -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notlike "$Dest\.venv\*" } |
    Unblock-File -ErrorAction SilentlyContinue
Set-Location $Dest
Say "      설치 위치: $Dest" DarkGray

# 2) Python 가상환경과 패키지
Say '[2/5] Python 패키지 설치 중... (처음에는 1~2분 걸립니다)'
$VenvPy = Join-Path $Dest '.venv\Scripts\python.exe'
if (-not (Test-Path $VenvPy)) {
    foreach ($launcher in 'py', 'python') {
        if (-not (Get-Command $launcher -ErrorAction SilentlyContinue)) { continue }
        if ($launcher -eq 'py') { & py -3 -m venv .venv } else { & python -m venv .venv }
        if (Test-Path $VenvPy) { break }
    }
    if (-not (Test-Path $VenvPy)) {
        Fail 'Python 을 찾지 못했습니다. Python 3.10 이상을 설치하고 PATH 설정을 확인하세요 (docs\PC.md 참고).'
    }
}
& $VenvPy -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'
if ($LASTEXITCODE -ne 0) {
    Remove-Item (Join-Path $Dest '.venv') -Recurse -Force -ErrorAction SilentlyContinue
    Fail 'Python 3.10 이상이 필요합니다. 새 버전을 설치한 뒤 install.bat 을 다시 실행하세요.'
}
& $VenvPy -m pip install --disable-pip-version-check -q -r requirements.txt
if ($LASTEXITCODE -ne 0) { Fail '패키지 설치에 실패했습니다. 인터넷 연결을 확인하고 다시 실행하세요.' }

# 3) 봇 토큰
Say '[3/5] 텔레그램 봇 토큰 확인 중...'
if (-not (Test-Path $EnvPath)) {
    [IO.File]::WriteAllText($EnvPath, [IO.File]::ReadAllText((Join-Path $Dest '.env.example')), $Utf8NoBom)
}
$token = Get-EnvValue 'TELEGRAM_BOT_TOKEN'
$username = $null
while ($true) {
    while (-not $token) {
        Say ''
        Say '  BotFather 에게 받은 봇 토큰을 붙여넣고 Enter 를 누르세요.' Yellow
        Say '  (붙여넣기: Ctrl+V 또는 마우스 오른쪽 클릭)' DarkGray
        $token = (Read-Host '  토큰').Trim()
    }
    $username = Test-Token $token
    if ($username -eq '') {
        Say '  [!] 토큰이 올바르지 않습니다. 다시 입력해 주세요.' Red
        $token = ''
        continue
    }
    break
}
Set-EnvValue 'TELEGRAM_BOT_TOKEN' $token
if ($null -eq $username) {
    Say '  [!] 텔레그램 서버에 연결하지 못했습니다. 봇은 백그라운드에서 계속 재시도합니다.' Yellow
    Say '      회사/학교 네트워크나 백신 프로그램이 텔레그램을 막는지 확인하세요.' Yellow
    Say '      (휴대폰 핫스팟에 연결해 다시 실행해 보면 원인을 구분할 수 있습니다)' Yellow
} else {
    Say "      연결 확인: @$username" Green
}

# 4) 자동 시작 등록 후 실행
Say '[4/5] 자동 시작 등록 및 봇 실행...'
$Vbs = Join-Path $Dest 'scripts\windows\start_hidden.vbs'
$Startup = [Environment]::GetFolderPath('Startup')
Set-Content -Path (Join-Path $Startup 'PortfolioBot.vbs') -Encoding ASCII `
    -Value ('CreateObject("WScript.Shell").Run """{0}""", 0, False' -f $Vbs)
Start-Process wscript.exe -ArgumentList ('"{0}"' -f $Vbs)
Say '      Windows 에 로그인할 때마다 자동으로 시작됩니다.' DarkGray

# 5) 봇 주인 등록
Say '[5/5] 봇 주인 등록 확인...'
if (Get-EnvValue 'TELEGRAM_CHAT_ID') {
    Say ''
    Say '완료! 봇이 백그라운드에서 실행 중입니다. 텔레그램에 "봇이 시작되었습니다" 메시지가 옵니다.' Green
} else {
    $link = if ($username) { "https://t.me/$username" } else { 'BotFather 가 보낸 메시지의 t.me 링크' }
    Say ''
    Say '  휴대폰 텔레그램에서 아래 링크를 열고, 봇 대화방 아래의 [시작] 버튼을 누르세요.' Yellow
    Say "      $link" White
    Say '  (등록될 때까지 이 창에서 기다립니다. 최대 10분)' DarkGray
    $deadline = (Get-Date).AddMinutes(10)
    $done = $false
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 3
        if (Get-EnvValue 'TELEGRAM_CHAT_ID') { $done = $true; break }
    }
    Say ''
    if ($done) {
        Say '완료! 등록되었습니다. 텔레그램으로 환영 메시지와 사용법이 옵니다.' Green
    } else {
        Say '아직 등록되지 않았습니다. 나중에라도 봇 대화방에서 [시작]을 누르면 자동으로 등록됩니다.' Yellow
    }
}
Say ''
Say "로그: $Dest\data\bot.log   (scripts\windows\open_log.bat)" DarkGray
Say '업데이트할 때는 새 ZIP 을 받아 그 안의 install.bat 을 다시 실행하면 됩니다.' DarkGray
