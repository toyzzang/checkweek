FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY checkweek/ checkweek/

RUN pip install --no-cache-dir .

# 태스크 데이터 영속성을 위한 볼륨 마운트 포인트
VOLUME /root/.checkweek

ENTRYPOINT ["checkweek"]
CMD ["list"]
