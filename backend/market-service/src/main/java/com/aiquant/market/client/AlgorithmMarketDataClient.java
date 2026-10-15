package com.aiquant.market.client;

import com.aiquant.market.api.HistoryResponse;
import com.aiquant.market.api.InstrumentCatalogResponse;
import com.aiquant.market.api.QuoteResponse;
import com.aiquant.market.api.TermStructureResponse;

public interface AlgorithmMarketDataClient {
    InstrumentCatalogResponse instruments();

    QuoteResponse quote(String symbol);

    HistoryResponse history(String symbol, int limit);

    TermStructureResponse termStructure(String rootSymbol);
}
