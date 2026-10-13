package com.aiquant.market.service;

import java.util.Locale;
import java.util.regex.Pattern;

import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

final class SymbolNormalizer {
    private static final Pattern SYMBOL = Pattern.compile("^[A-Z]{1,4}[A-Z0-9]{0,8}$");

    private SymbolNormalizer() {
    }

    static String normalize(String rawSymbol) {
        String normalized = rawSymbol == null ? "" : rawSymbol.trim().toUpperCase(Locale.ROOT);
        if (!SYMBOL.matcher(normalized).matches()) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY, "Invalid futures symbol");
        }
        return normalized;
    }
}
