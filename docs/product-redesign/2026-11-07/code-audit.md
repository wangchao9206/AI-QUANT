# 现状审查与证据边界

审查基线：仓库 `4dc61699a108bcdea4047c7df3acef7b9bd1b9da`。方式是静态代码和已保存研究输出审查，不是真实投资者可用性测试，没有业务行为埋点基线。默认导航不代表每一租户最终显示的菜单。

| ID | 可核验事实 | 来源 | 设计含义（推断，待验证） |
| --- | --- | --- | --- |
| F01 | AppShell默认16个主入口；用户菜单可覆盖默认项；移动端仍逐项展示并横向滑动 | frontend/src/layouts/AppShell.vue:baseNavigation/navigation/mobile-nav | 入口按能力名组织，不能假设新手知道任务起点；不宜直接以16推算真实认知成本 |
| F02 | router同时有market详情、strategy详情、live、options、backtest、paper、research及10个缠论子入口 | frontend/src/router.ts；features/chanlun/ChanlunNavigation.vue | 同一品种存在多套工作环境，缠论中心本身也是完整小产品 |
| F03 | useMarketStore/useDashboard已有共享symbol、最近访问及路径参数；instrumentPath/researchPath主要传symbol | stores/market.ts；composables/useDashboard.ts；utils/marketNavigation.ts | 已有部分桥梁，应补足时间、实际合约、来源事件和策略版本，不是从零开发导航 |
| F04 | ResearchWorkbench调用服务器风险核算，但savePlan/saveReview写本地planJournal；提供JSON导出；账户情景手工输入 | components/ResearchWorkbench.vue；utils/planJournal.ts | 服务器核算不等于跨设备计划持久化，计划和实际模拟头寸未形成统一事实来源 |
| F05 | 工作流已有不可变发布版本、debug、backtest、shadow/evidence和PaperTradingView版本选择衔接 | services/workflows.ts；views/StrategyWorkflowView.vue；views/PaperTradingView.vue | 版本和证据链值得保留复用，不能只重画页面后丢掉 |
| F06 | LiveView持有本页symbol/frequency/bars/depth状态，使用共享目录但有独立选择；inspectAlert回到实际合约900秒图 | views/LiveView.vue | 近期预警—图表已有联动，仍应纳入统一决策对象及时间上下文 |
| F07 | MonitorPanel同时展示多批研究、多个预警模板、任务配置与事件记录；API持久化任务、版本、事件和租约 | components/MonitorPanel.vue；services/monitoring.ts；market/monitor/MonitorStore.java | 研究证据、订阅管理、当下决策不宜全堆在一页；历史事件不应为减页而删除 |
| F08 | 基础、多周期/缠论、通道研究复用既有历史；默认候选仍为历史标签频率，tradeQualified=false | config/outcome-patterns.json；config/multifactor-patterns.json；config/line-patterns.json；algorithm_service/*monitor.py | 需要分开“规则满足/历史频率/校准预测/可执行计划”，不能统一叫置信胜率 |
| F09 | fusion_engine在eligible中混合实证和文化参考，再加权生成分数与confidence；ResearchWorkbench另有默认EMPIRICAL模式 | engines/fusion_engine.py:evaluate_all；components/ResearchWorkbench.vue | 两种决策口径同时存在，需要统一默认行动依据；建议文化内容不影响概率/仓位，但这是方案取舍而非当前改动 |
| F10 | AppShell全局“状态可观测”文字和状态点不是连接健康的实时绑定；各页面另有FreshnessBadge等状态 | layouts/AppShell.vue；components/FreshnessBadge.vue | 统一可核验的数据状态，避免绿点被误认为所有页面都在实时交易 |
| F11 | OptionsView提供真实链、Black76/BSM及单腿到期情景；研究脚本另完成168个结构快照情景，没有期权历史盈利回测 | views/OptionsView.vue；algorithm_service/options.py；docs/options.md；docs/research/options-opportunities-2026-11-07.md | 多腿风险台有价值，但不能承诺当前已有组合保证金、历史IV分位或期权正期望 |
| F12 | 通道/斜线和手画工具已在TongdaxinChart；手画按浏览器合约周期保存，不参与后台自动模型 | components/TongdaxinChart.vue；utils/chartDrawings.ts；backtesting/line_geometry.py | 技术指标、画线、缠论应成为工作台工具层；个人标注与冻结模型证据需区分 |
| F13 | 学习、导师、书籍感悟、个人总结和研究库均独立顶级入口；个人总结还含规则训练/版本实验 | views/LearnView.vue；MentorsView.vue；BookReflectionsView.vue；PersonalSummaryView.vue；ResearchLibraryView.vue | 内容与交易任务重要性不等同；学习资料可次级化，个人训练和复盘能力不能随内容入口一起隐藏 |
| F14 | 有身份、租户、菜单权限、模拟账本和隔离审计；并非真实券商下单系统 | services/auth.ts；backend/identity-service；backend/paper-trading-service；docs/accounts.md | 重设计须保持隔离、审计与老数据，不以新页面绕过权限或把模拟说成实盘 |
| F15 | 多个研究模板有明确WARMING/STALE/OUT_OF_SCOPE状态，缺数据不补造；实证研究保存失败结果 | algorithm_service/monitor_rules.py；*monitor.py；docs/research/data | 基础可信机制是资产，新的摘要界面必须保持可追溯和不确定性，不将限制藏掉 |

## 不应被当成事实的判断

“多数用户喜欢某一导航”“某页面转化低”“新首页能提升预测准确率”“减少入口能提高收益”均无真实用户或对照数据支持。本次只提出可测试假设。10类模拟视角用于拓宽问题空间；3种专家视角是分析框架，不是被聘请的真人专家背书。

## 已有桥梁与真正断点

已有桥梁：品种详情与研究路径；工作流版本—shadow—模拟；预警—实际合约图表；部分研究计划快照与本机复盘。

真正待统一的是：谁的哪一个决策对象、基于何时什么行情与证据、对应哪一版本、处于研究/准备/监控/模拟哪一状态，以及失败后如何回到同一个对象。方案不能退化为只换五个菜单。
