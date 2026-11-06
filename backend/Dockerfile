# One reactor build shared by every Java runtime target.
FROM maven:3.9.11-eclipse-temurin-17 AS build
WORKDIR /workspace
COPY . .
RUN --mount=type=cache,id=aiquant-maven,target=/root/.m2,sharing=locked mvn -B -s maven-settings.xml -Dmaven.wagon.http.retryHandler.count=5 package

FROM eclipse-temurin:17.0.16_8-jre-jammy AS runtime
RUN command -v curl && test -s /etc/ssl/certs/ca-certificates.crt \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app app
WORKDIR /app
USER 10001:10001
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75", "-XX:+ExitOnOutOfMemoryError", "-jar", "/app/app.jar"]

FROM runtime AS identity-service
COPY --from=build --chown=app:app /workspace/identity-service/target/identity-service-*.jar app.jar
EXPOSE 8085

FROM runtime AS gateway-service
COPY --from=build --chown=app:app /workspace/gateway-service/target/gateway-service-*.jar app.jar
EXPOSE 8080

FROM runtime AS market-service
COPY --from=build --chown=app:app /workspace/market-service/target/market-service-*.jar app.jar
EXPOSE 8081

FROM runtime AS strategy-service
COPY --from=build --chown=app:app /workspace/strategy-service/target/strategy-service-*.jar app.jar
EXPOSE 8082

FROM runtime AS paper-trading-service
COPY --from=build --chown=app:app /workspace/paper-trading-service/target/paper-trading-service-*.jar app.jar
EXPOSE 8083

FROM runtime AS chanlun-service
COPY --from=build --chown=app:app /workspace/chanlun-service/target/chanlun-service-*.jar app.jar
EXPOSE 8084
