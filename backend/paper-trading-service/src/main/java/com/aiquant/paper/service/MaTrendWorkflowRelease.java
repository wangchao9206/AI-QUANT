package com.aiquant.paper.service;

import com.fasterxml.jackson.databind.JsonNode;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HexFormat;
import java.util.TreeMap;
import java.util.regex.Pattern;

/** The dedicated replay evaluates a fixed protocol, so a diagram cannot change its semantics. */
final class MaTrendWorkflowRelease {
    static final String DRAFT_KIND = "MA_TREND_15M";
    static final String ENGINE = "workflow-ma-trend-15m-v1";
    private static final BigDecimal MIN_TARGET = new BigDecimal("0.01");
    private static final BigDecimal MAX_TARGET = new BigDecimal("50");
    private static final Pattern ID = Pattern.compile("[A-Za-z0-9_-]{1,64}");
    // Pin the node parameters and connections of maTrendTemplate, excluding diagram layout and labels.
    private static final String GRAPH_SHA256 = "126eaf9c72e935e293648c01dd1cecf75326138e4301234ee84685f0c06f6329";

    private MaTrendWorkflowRelease() {}

    static boolean isDraft(JsonNode definition) {
        return DRAFT_KIND.equals(definition.path("draftKind").asText());
    }

    static BigDecimal validate(JsonNode definition) {
        if (!isDraft(definition) || definition.path("schemaVersion").asInt() != 1
            || !definition.path("nodes").isArray() || !definition.path("edges").isArray()
            || !GRAPH_SHA256.equals(graphHash(definition))) {
            throw new IllegalArgumentException("均线策略的日线配置与内置模板不一致，请从模板重新配置");
        }
        JsonNode execution = definition.path("maTrendExecution");
        JsonNode target = execution.path("takeProfitPct");
        if (!execution.isObject() || execution.size() != 1 || !target.isNumber()) {
            throw new IllegalArgumentException("请填写止盈目标百分比");
        }
        BigDecimal percent = target.decimalValue().stripTrailingZeros();
        if (percent.compareTo(MIN_TARGET) < 0 || percent.compareTo(MAX_TARGET) > 0 || percent.scale() > 2) {
            throw new IllegalArgumentException("止盈目标须为 0.01% 至 50%，最多两位小数");
        }
        return percent;
    }

    private static String graphHash(JsonNode definition) {
        var rows = new ArrayList<String>();
        for (JsonNode node : definition.path("nodes")) {
            String row = "node|" + token(node.path("id")) + "|" + token(node.path("type"));
            JsonNode params = node.path("params");
            if (!params.isObject()) {
                throw new IllegalArgumentException("均线策略的节点参数无效");
            }
            var fields = new TreeMap<String, JsonNode>();
            params.fields().forEachRemaining(field -> fields.put(field.getKey(), field.getValue()));
            var values = new StringBuilder(row);
            fields.forEach((key, value) -> {
                if (!ID.matcher(key).matches() || !(value.isTextual() || value.isIntegralNumber())) {
                    throw new IllegalArgumentException("均线策略的节点参数无效");
                }
                values.append('|').append(key).append('|').append(value);
            });
            rows.add(values.toString());
        }
        for (JsonNode edge : definition.path("edges")) {
            rows.add("edge|" + token(edge.path("source")) + "|" + token(edge.path("sourcePort"))
                + "|" + token(edge.path("target")) + "|" + token(edge.path("targetPort")));
        }
        Collections.sort(rows);
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                .digest(String.join("\n", rows).getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("缺少 SHA-256 算法", impossible);
        }
    }

    private static String token(JsonNode value) {
        if (!value.isTextual() || !ID.matcher(value.asText()).matches()) {
            throw new IllegalArgumentException("均线策略的节点或端口编号无效");
        }
        return value.asText();
    }
}
