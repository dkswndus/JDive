import os

# 테스트가 실제 Sentry 로 이벤트를 보내지 않도록, .env 에 DSN 이 있어도 여기서 비워 둔다.
os.environ["SENTRY_DSN"] = ""
