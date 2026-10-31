# 내 PC를 서버로 쓰기 (Windows)

클라우드 서버 대신, 항상 켜져 있는 Windows PC에서 봇을 돌리는 방법입니다. 처음 설정은 20~30분 정도 걸립니다.

## 먼저 알아둘 점

- **PC가 켜져 있고 Windows에 로그인된 상태여야 봇이 동작합니다.** 화면이 꺼지거나 잠금 화면이어도 괜찮지만, **절전 모드에 들어가면 멈춥니다**(8단계에서 끕니다).
- Windows 업데이트 등으로 **재부팅되면, 다시 로그인해야 봇이 자동으로 시작**됩니다.
- **클라우드와 PC에서 동시에 실행하지 마세요.** 텔레그램은 봇 하나당 연결을 하나만 허용합니다. 같은 PC에서 두 번 실행하는 것은 봇이 스스로 막습니다.
- 고정 IP나 공유기 포트 개방은 필요 없습니다.

---

## 1. 텔레그램 봇 만들기

[클라우드 가이드의 1단계](DEPLOY.md#1단계-텔레그램-봇-만들기-5분)와 같습니다. BotFather에서 받은 **토큰**을 준비하세요.

## 2. 프로그램 2개 설치

1. **Python 3.12**: <https://www.python.org/downloads/> 에서 받습니다.
   - 설치 첫 화면에서 **"Add python.exe to PATH"를 반드시 체크**한 뒤 Install Now를 누릅니다.
2. **Git**: <https://git-scm.com/download/win> 에서 받습니다. 설치 옵션은 모두 기본값 그대로 두면 됩니다.

## 3. 코드 받기

시작 메뉴에서 **명령 프롬프트**(cmd)를 열고 아래를 붙여넣습니다.

```bat
cd /d C:\
git clone https://github.com/gamhu0919-sudo/TradingView-for-me.git portfolio-bot
```

`C:\portfolio-bot` 폴더가 생깁니다. 한글이나 공백이 없는 경로가 가장 안전합니다.

> 나중에 저장소를 비공개로 바꾸면, 처음 `git clone`이나 업데이트할 때 GitHub 로그인 창이 한 번 뜹니다. 로그인하면 그 뒤로는 자동입니다.

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
| 최신 코드로 업데이트 | `update.bat` (중지, 업데이트, 재시작을 한 번에) |
| 로그 보기 | `open_log.bat` (`data\bot.log`) |
| 자동 시작 해제 | `uninstall_autostart.bat` |

- **데이터 위치:** 보유 종목과 일정은 `C:\portfolio-bot\data\portfolio.db` 에 있습니다. 매일 07:10에 `data\backups\` 에 요일별 백업이 만들어집니다.
- **PC 고장에 대비한 백업:** 가끔 텔레그램에서 `/export` 로 CSV를 받아 두세요.
- **나중에 클라우드로 옮길 때:** PC 봇을 먼저 중지(`uninstall_autostart.bat`)합니다. 그다음 클라우드 봇에게 `/export` 로 받은 CSV를 보내면 보유 종목이 그대로 옮겨집니다. 알림 일정은 다시 등록해야 합니다.

## 문제 해결

| 증상 | 확인할 것 |
|---|---|
| `setup.bat` 에서 "Python was not found" | Python을 다시 설치하면서 **Add python.exe to PATH** 를 체크했는지 |
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
