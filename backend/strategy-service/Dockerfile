FROM maven:3.9.11-eclipse-temurin-17 AS build
WORKDIR /workspace
COPY pom.xml ./
COPY gateway-service/pom.xml gateway-service/pom.xml
COPY market-service/pom.xml market-service/pom.xml
COPY strategy-service/pom.xml strategy-service/pom.xml
COPY paper-trading-service/pom.xml paper-trading-service/pom.xml
COPY maven-settings.xml ./maven-settings.xml
COPY gateway-service/src gateway-service/src
COPY market-service/src market-service/src
COPY strategy-service/src strategy-service/src
COPY paper-trading-service/src paper-trading-service/src
RUN --mount=type=cache,id=aiquant-maven,target=/root/.m2,sharing=locked mvn -B -s maven-settings.xml -Dmaven.wagon.http.retryHandler.count=5 package

FROM eclipse-temurin:17.0.16_8-jre-jammy
RUN command -v curl && test -s /etc/ssl/certs/ca-certificates.crt \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app app
WORKDIR /app
COPY --from=build --chown=app:app /workspace/strategy-service/target/strategy-service-*.jar app.jar
USER 10001:10001
EXPOSE 8082
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75", "-XX:+ExitOnOutOfMemoryError", "-jar", "/app/app.jar"]
