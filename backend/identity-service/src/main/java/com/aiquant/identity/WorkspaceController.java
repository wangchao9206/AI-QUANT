package com.aiquant.identity;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/auth/workspace")
final class WorkspaceController {
    private final Accounts accounts;private final WorkspaceDocuments documents;
    WorkspaceController(Accounts accounts,WorkspaceDocuments documents){this.accounts=accounts;this.documents=documents;}
    @GetMapping("/preferences") Object preferences(HttpServletRequest request){return documents.get(accounts.require(request,false,false),documents.preferences());}
    @PostMapping("/preferences") Object preferences(@RequestBody WorkspaceDocuments.Save body,HttpServletRequest request){return documents.save(accounts.require(request,true,false),documents.preferences(),body);}
    @GetMapping("/charts/{symbol}/{period}") Object chart(@PathVariable String symbol,@PathVariable String period,HttpServletRequest request){return documents.get(accounts.require(request,false,false),documents.chart(symbol,period));}
    @PostMapping("/charts/{symbol}/{period}") Object chart(@PathVariable String symbol,@PathVariable String period,@RequestBody WorkspaceDocuments.Save body,HttpServletRequest request){return documents.save(accounts.require(request,true,false),documents.chart(symbol,period),body);}
}
