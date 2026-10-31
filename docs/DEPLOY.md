# 클라우드 서버 배포 가이드

전체 소요 시간은 약 30~40분입니다. **Google Cloud 무료 서버(e2-micro)** 를 기준으로 설명하고, 끝에 Oracle Cloud 대안을 덧붙였습니다.

이 봇은 개인 API 키가 없고 고정 IP도 필요 없어서, 미국 리전 무료 서버에서도 문제없이 동작합니다.

---

## 1단계. 텔레그램 봇 만들기 (5분)

1. 텔레그램에서 **@BotFather** 를 검색해 대화를 시작합니다.
2. `/newbot` 을 보냅니다.
3. 봇 이름을 입력합니다 (예: `내 포트폴리오`).
4. 봇 아이디를 입력합니다. 반드시 `bot`으로 끝나야 합니다 (예: `my_pf_alert_bot`).
5. 받은 **토큰**(`123456789:AA...` 형태)을 메모해 둡니다. 비밀번호처럼 다루고 누구에게도 보여주지 마세요.
6. 방금 만든 봇과의 대화방을 열어 둡니다. chat_id는 4단계에서 봇이 직접 알려줍니다.

## 2단계. Google Cloud 무료 서버 만들기 (15분)

1. <https://cloud.google.com> 에 가입합니다. 결제 카드 등록이 필요하지만, 무료 등급 범위 안에서는 요금이 청구되지 않습니다.
2. 콘솔에서 **Compute Engine → VM 인스턴스 → 인스턴스 만들기** 로 이동합니다. 처음이면 API 사용 설정 버튼을 누릅니다.
3. 다음과 같이 설정합니다. **무료 등급 조건이라 그대로 따라야 합니다.**

   | 항목 | 값 |
   |---|---|
   | 이름 | `portfolio-bot` |
   | 리전 | `us-west1`(오리건), `us-central1`(아이오와), `us-east1`(사우스캐롤라이나) 중 하나 |
   | 머신 유형 | **e2-micro** |
   | 부팅 디스크 | Ubuntu 24.04 LTS, **표준 영구 디스크(Standard persistent disk)**, 30GB 이하 |
   | 방화벽 | HTTP/HTTPS 체크하지 않음 (필요 없음) |

   > ⚠️ 부팅 디스크 기본값은 '균형 있는 영구 디스크(Balanced)'인데, 이건 무료가 아닙니다. 반드시 **표준(Standard)** 으로 바꾸세요.

4. **만들기** 를 누르고 1~2분 기다립니다.
5. **예산 알림을 설정합니다 (권장).** 결제 → 예산 및 알림 → 예산 만들기 → 금액 `$1`. 예상치 못한 요금이 생기면 바로 메일이 옵니다.
   > 외부 IP 주소의 과금 정책은 자료마다 설명이 달라서 확실하지 않습니다. 며칠 뒤 결제 보고서에서 청구 금액이 0원인지 한 번 확인하세요.

## 3단계. 서버에 접속해 설치하기 (10분)

VM 목록에서 **SSH** 버튼을 누르면 브라우저에 터미널이 열립니다. 아래 명령을 차례로 붙여넣습니다.

```bash
# 1) 메모리 1GB 서버라 스왑 1GB 추가 (빌드 안정성)
sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# 2) Docker 설치
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

여기서 **SSH 창을 닫고 다시 엽니다**(docker 권한 적용). 그다음:

```bash
# 3) 코드 받기 (공개 저장소인 경우)
git clone https://github.com/gamhu0919-sudo/TradingView-for-me.git
cd TradingView-for-me

# 4) 설정 파일 만들기
cp .env.example .env
nano .env
```

> **저장소가 비공개라면** 위의 `git clone` 대신 아래 순서로 받습니다. 서버에 **읽기 전용 배포 키(Deploy key)** 를 등록하는 방식입니다. 이 키로는 이 저장소 하나만, 그것도 읽기만 할 수 있습니다.
>
> ```bash
> ssh-keygen -t ed25519 -C "portfolio-bot" -f ~/.ssh/id_ed25519 -N ""
> cat ~/.ssh/id_ed25519.pub        # 출력된 한 줄(ssh-ed25519 ...)을 복사
> ```
>
> 1. GitHub 저장소 → **Settings → Deploy keys → Add deploy key**
> 2. Title은 `portfolio-bot`으로 하고, Key에 복사한 줄을 붙여넣습니다. **Allow write access는 체크하지 않습니다.**
> 3. 서버로 돌아와 아래를 실행합니다.
>
> ```bash
> ssh -o StrictHostKeyChecking=accept-new -T git@github.com   # "successfully authenticated" 가 나오면 성공
> git clone git@github.com:gamhu0919-sudo/TradingView-for-me.git
> cd TradingView-for-me
> cp .env.example .env
> nano .env
> ```
>
> 이후 `git pull` 업데이트도 같은 키로 동작합니다.

`nano` 편집기에서 `TELEGRAM_BOT_TOKEN=` 뒤에 1단계에서 받은 토큰을 붙여넣습니다. `Ctrl+O`, `Enter`로 저장하고 `Ctrl+X`로 나옵니다.

```bash
chmod 600 .env                 # 본인만 읽을 수 있게
docker compose up -d --build   # 봇 빌드 및 실행 (처음엔 2~3분)
```

## 4단계. chat_id 등록 (2분)

1. 텔레그램에서 내 봇에게 `/start` 를 보냅니다.
2. 봇이 `chat_id: 123456789` 를 알려줍니다. 아직 chat_id가 없어서 설정 모드로 응답하는 것입니다.
3. 서버에서 `.env` 를 다시 열어 그 값을 넣습니다.

```bash
nano .env                          # TELEGRAM_CHAT_ID=123456789
docker compose up -d --force-recreate
```

4. 봇이 **"처음 실행되었습니다"** 메시지와 도움말을 보내면 완료입니다. 🎉

## 5단계. 보유 종목 입력

텔레그램에서 입력합니다.

```
/add 삼성전자 30 180000
/add 애플 10 300 @1380
/add 비트코인 0.05 95000000
/cash 2000000
/now
```

`/schedule` 로 알림 일정을 확인하고 원하는 대로 바꾸세요.

---

## 운영

| 하고 싶은 일 | 명령 (서버의 `TradingView-for-me` 폴더에서) |
|---|---|
| 로그 보기 | `docker compose logs -f --tail 100` |
| 재시작 | `docker compose restart` |
| 코드 업데이트 | `git pull && docker compose up -d --build` |
| 중지 | `docker compose down` (데이터는 보존) |
| 데이터베이스 파일 꺼내기 | `docker compose cp bot:/app/data/portfolio.db ./portfolio.db` |

- **데이터 위치:** 보유 종목과 일정은 도커 볼륨(`botdata`)의 `portfolio.db`에 저장됩니다. 매일 07:10에 같은 볼륨의 `backups/` 에 요일별 백업이 만들어집니다.
- **서버 밖 백업:** 서버 자체가 사라질 때를 대비해 가끔 `/export` 로 CSV를 받아 두세요. 그 파일을 봇에게 보내면 그대로 복원됩니다.
- **봇이 멈췄는지 확인:** 서버가 재부팅되면 컨테이너가 자동으로 다시 시작되고(`restart: unless-stopped`), 봇이 "✅ 봇이 시작되었습니다" 메시지를 보냅니다. 정기 리포트가 오지 않으면 로그를 확인하세요.

## 대안: Oracle Cloud 무료 서버

서울 리전을 쓰고 싶다면 Oracle Cloud Always Free도 괜찮습니다.

1. 가입할 때 **홈 리전을 서울(ap-seoul-1)** 로 고릅니다. 홈 리전은 나중에 바꿀 수 없습니다.
2. 인스턴스 Shape는 **VM.Standard.E2.1.Micro (AMD, 1GB)** 를 고르고, 이미지는 Ubuntu로 합니다. Ampere A1은 서울에서 재고가 자주 부족합니다.
3. 3단계부터는 위와 동일합니다.
4. ⚠️ Oracle은 7일 동안 CPU·네트워크 사용률이 낮은 무료 VM을 '유휴'로 보고 회수할 수 있습니다. 이 봇은 가벼워서 해당될 가능성이 높습니다. 계정을 **Pay As You Go** 로 전환하면 회수 대상에서 빠지는 것으로 알려져 있습니다. 무료 자원만 쓰면 요금은 나오지 않고, 이 경우에도 예산 알림을 꼭 설정하세요.
