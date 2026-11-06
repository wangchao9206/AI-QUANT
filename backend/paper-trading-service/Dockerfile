FROM maven:3.9.11-eclipse-temurin-17 AS build
WORKDIR /workspace
COPY . .
RUN --mount=type=cache,id=aiquant-maven,target=/root/.m2,sharing=locked mvn -B -s maven-settings.xml -Dmaven.wagon.http.retryHandler.count=5 package

FROM eclipse-temurin:17.0.16_8-jre-jammy
RUN command -v curl && test -s /etc/ssl/certs/ca-certificates.crt \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app app
WORKDIR /app
COPY --from=build --chown=app:app /workspace/paper-trading-service/target/paper-trading-service-*.jar app.jar
USER 10001:10001
EXPOSE 8083
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75", "-XX:+ExitOnOutOfMemoryError", "-jar", "/app/app.jar"]
