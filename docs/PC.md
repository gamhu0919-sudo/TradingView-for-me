# 내 PC를 서버로 쓰기 (Windows)

클라우드 서버 대신, 항상 켜져 있는 Windows PC에서 봇을 돌리는 방법입니다. 처음 설정은 20~30분 정도 걸리고, Python 3.10 이상이 필요합니다.

## 먼저 알아둘 점

- **PC가 켜져 있고 Windows에 로그인된 상태여야 봇이 동작합니다.** 화면이 꺼지거나 잠금 화면이어도 괜찮지만, **절전 모드에 들어가면 멈춥니다**(8단계에서 끕니다).
- Windows 업데이트 등으로 **재부팅되면, 다시 로그인해야 봇이 자동으로 시작**됩니다.
- **클라우드와 PC에서 동시에 실행하지 마세요.** 텔레그램은 봇 하나당 연결을 하나만 허용합니다. 같은 PC에서 두 번 실행하는 것은 봇이 스스로 막습니다.
- 고정 IP나 공유기 포트 개방은 필요 없습니다.

---

## 1. 텔레그램 봇 만들기

[클라우드 가이드의 1단계](DEPLOY.md#1단계-텔레그램-봇-만들기-5분)와 같습니다. BotFather에서 받은 **토큰**을 준비하세요.

## 2. Python 확인

**Python 3.10 이상**이면 됩니다. 이미 3.10이 설치돼 있다면 새로 설치할 필요가 없고, 아래처럼 '명령어로 실행되는지'만 확인하면 됩니다.

1. 키보드의 **Windows 키**를 누르고 `cmd` 를 입력한 뒤 **명령 프롬프트**를 엽니다. 검은 창이 뜹니다.
2. 아래를 입력하고 Enter를 누릅니다.
   ```
   py --version
   ```
3. 결과에 따라 이렇게 합니다.
   - **`Python 3.10.x` 처럼 버전이 나오면 끝입니다.** 3단계로 넘어가세요.
   - `'py'은(는) 내부 또는 외부 명령... 이 아닙니다` 가 나오면 `python --version` 을 입력해 봅니다. 여기서 버전이 나와도 끝입니다.
   - 둘 다 안 되거나 Microsoft Store가 열리면 **PATH 설정**이 필요합니다(아래).

### PATH 설정이란?

PATH는 Windows가 `python` 같은 명령어를 입력받았을 때 **프로그램을 찾아볼 폴더 목록**입니다. Python 폴더가 이 목록에 없으면 Python이 설치돼 있어도 명령 프롬프트가 찾지 못합니다. Python 설치 프로그램의 **"Add python.exe to PATH"** 체크박스가 바로 이 목록에 Python 폴더를 추가하는 옵션입니다.

이미 설치된 Python에 PATH를 추가하려면:

1. **설정 → 앱 → 설치된 앱**(Windows 10은 '앱 및 기능')에서 **Python 3.10.x** 를 찾습니다.
2. 오른쪽 **⋯** 버튼(또는 항목 클릭) → **수정** 을 누릅니다. Python 설치 창이 열립니다.
3. **Modify** → **Next** 를 누릅니다.
4. **Advanced Options** 화면에서 **"Add Python to environment variables"** 를 체크하고 **Install** 을 누릅니다.
5. 열려 있던 명령 프롬프트를 **닫고 새로 연 뒤** `python --version` 으로 다시 확인합니다.

## 3. 코드 받기 (ZIP 다운로드)

Git(코드를 내려받고 업데이트하는 개발자용 프로그램)은 **설치하지 않아도 됩니다.** 웹브라우저에서 ZIP 파일로 받으면 됩니다.

1. <https://github.com/gamhu0919-sudo/TradingView-for-me> 에 들어가 초록색 **Code** 버튼 → **Download ZIP** 을 누릅니다.
2. 다운로드된 `TradingView-for-me-main.zip` 을 **오른쪽 클릭 → 속성** → 아래쪽 **"차단 해제"** 체크 → **확인**.
   (인터넷에서 받은 파일이라 이걸 안 하면 실행할 때 "Windows의 PC 보호" 경고가 뜹니다. 그때는 **추가 정보 → 실행** 을 누르면 됩니다.)
3. ZIP을 **오른쪽 클릭 → 압축 풀기** 를 누르고 대상 폴더를 `C:\` 로 지정합니다.
4. 생긴 `C:\TradingView-for-me-main` 폴더 이름을 **`portfolio-bot`** 으로 바꿉니다.
5. `C:\portfolio-bot\scripts\windows\setup.bat` 파일이 있으면 제대로 된 것입니다.

> 나중에 저장소를 비공개로 바꿔도, 브라우저에서 GitHub에 로그인돼 있으면 같은 방법으로 받을 수 있습니다.

## 4. 설치 스크립트 실행

파일 탐색기에서 `C:\portfolio-bot\scripts\windows` 폴더를 엽니다. 아래부터 나오는 파일은 모두 이 폴더에 있습니다.

1. **`setup.bat`** 을 더블클릭합니다. 필요한 패키지를 설치하는 데 1~2분 걸립니다.
2. 메모장이 열리면 `TELEGRAM_BOT_TOKEN=` 뒤에 토큰을 붙여넣고 **저장한 뒤 닫습니다.**

## 5. 시세 조회 시험

**`preview.bat`** 을 더블클릭합니다. 예시 포트폴리오 리포트(코스피, 삼성전자, 애플, 비트코인 등)가 창에 출력되면 정상입니다.

## 6. chat_id 등록

1. **`start_bot.bat`** 을 더블클릭합니다. 검은 창이 열린 채로 봇이 실행됩니다.
2. 텔레그램에서 내 봇에게 `/start` 를 보내면 봇이 **chat_id** 를 알려줍니다.
3. 검은 창을 닫습니다(봇 중지).
4. `C:\portfolio-bot\.env` 를 메모장으로 열어 `TELEGRAM_CHAT_ID=` 뒤에 그 숫자를 넣고 저장합니다.

## 7. 자동 시작 등록

**`install_autostart.bat`** 을 더블클릭합니다.

- 봇이 **창 없이 백그라운드에서** 실행됩니다.
- 텔레그램에 **"처음 실행되었습니다"** 메시지가 오면 성공입니다. 🎉
- 앞으로는 Windows에 로그인할 때마다 자동으로 시작됩니다. 관리자 권한은 필요 없습니다.
- 봇이 오류로 꺼지면 30초 뒤 자동으로 다시 켜집니다.

## 8. 절전 모드 끄기 (중요)

- **설정 → 시스템 → 전원(및 배터리) → 화면 및 절전**에서 **"절전 모드로 전환"** 을 **"안 함"** 으로 바꿉니다. 화면 끄기는 그대로 두어도 됩니다.
- **노트북이라면** 제어판 → 전원 옵션 → **"덮개를 닫으면 수행할 작업"** 을 **"아무 것도 안 함"** 으로 바꾸고, 전원 어댑터를 연결해 두세요.

---

## 사용하면서

`scripts\windows` 폴더의 파일을 더블클릭하면 됩니다.

| 하고 싶은 일 | 파일 |
|---|---|
| 봇 중지 | `stop_bot.bat` |
| 봇 다시 시작 | `install_autostart.bat` (다시 실행해도 괜찮음) |
| 최신 코드로 업데이트 | ① `stop_bot.bat` 실행 ② 새 ZIP을 받아 압축을 풀고, 나온 폴더 안의 파일을 모두 `C:\portfolio-bot` 에 붙여넣기(덮어쓰기) ③ `update.bat` 실행. `.env` 와 `data` 폴더는 ZIP에 없어서 그대로 유지됩니다 |
| 로그 보기 | `open_log.bat` (`data\bot.log`) |
| 자동 시작 해제 | `uninstall_autostart.bat` |

- **데이터 위치:** 보유 종목과 일정은 `C:\portfolio-bot\data\portfolio.db` 에 있습니다. 매일 07:10에 `data\backups\` 에 요일별 백업이 만들어집니다.
- **PC 고장에 대비한 백업:** 가끔 텔레그램에서 `/export` 로 CSV를 받아 두세요.
- **나중에 클라우드로 옮길 때:** PC 봇을 먼저 중지(`uninstall_autostart.bat`)합니다. 그다음 클라우드 봇에게 `/export` 로 받은 CSV를 보내면 보유 종목이 그대로 옮겨집니다. 알림 일정은 다시 등록해야 합니다.

## 문제 해결

| 증상 | 확인할 것 |
|---|---|
| `setup.bat` 에서 "Python was not found" | 2단계의 **PATH 설정**을 했는지 |
| 정기 알림이 안 옴 | PC가 절전 모드에 들어가지 않았는지, `open_log.bat` 로그에 오류가 있는지 |
| 로그에 `Conflict` 오류 | 다른 곳(클라우드 서버 등)에서 같은 봇이 실행 중인지 |
| 봇이 응답하지 않음 | `.env` 의 토큰과 chat_id가 맞는지 확인한 뒤 `install_autostart.bat` 를 다시 실행 |

## Mac이라면

터미널에서 아래를 실행하면 됩니다. 로그인할 때 자동으로 시작되게 하려면 `launchd` 설정이 따로 필요하니, 원하시면 요청해 주세요.

```bash
git clone https://github.com/gamhu0919-sudo/TradingView-for-me.git ~/portfolio-bot && cd ~/portfolio-bot
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env && open -e .env     # 토큰 입력 후 저장
LOG_FILE=data/bot.log nohup .venv/bin/python -m bot >/dev/null 2>&1 &
```

Mac은 **시스템 설정 → 에너지**에서 "디스플레이가 꺼져 있을 때 자동으로 잠자기 방지"를 켜두세요.
