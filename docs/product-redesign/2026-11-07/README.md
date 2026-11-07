# AI-QUANT 产品重设计交付

日期：2026-11-07。经用户授权，完成10类投资者角色模拟访谈和3种资深产品专家模拟视角评审。真实受访者与受聘专家均为0；没有伪造用户行为、满意度或收益改善。

## 从哪里开始

- [最终具体方案](redesign-plan.md)：定位、五入口、全部旧模块去留、共享对象、预测/辅助/策略/指标规格、实施依赖与验收。
- [56页完整报告](../../../output/product-redesign-2026-11-07/ai-quant-product-redesign-2026-11-07.pdf)：包含原始模拟问答、三份独立评审及最终取舍。
- [离线可点击原型](../../../output/product-redesign-2026-11-07/prototype.html)：浏览器打开即可。全部为演示数据；不联网、不创建后台任务或成交，刷新重置内存状态。
- [专家意见取舍](expert-decisions.md)：12项裁决及保留分歧。
- [37条需求去向](requirements-traceability.json)：35条映射本方案验收，2条完整组合/企业套保需求明确后置，待独立立项定义验收。计数不是用户支持率。

## 核心设计

以“今日、机会、交易台、策略、复盘”组织任务，以实际合约、观察时点、证据和计划版本贯穿流程。允许只看图、继续等待及直接恢复专业工作区，不要求所有用户走向导。缠论、画线、期权链和量化实验保留专业深度；资料内容和旧记录保留。

先实现一条纵向切片：预警原事件 → 当时图表/反证 → 服务端计划版本 → 观察/模拟意图或拒绝 → 原依据复盘。菜单整理随后渐进迁移。预测质量独立做新数据验证，不把导航变简洁解释为模型变准。

## 原始材料

- [P01至P04](investors-a.md)：零基础、半年经验期权小账户、兼职、主观趋势/缠论。
- [P05至P07](investors-b.md)：日内、量化CTA、产业/套保。
- [P08至P10](investors-c.md)：专业期权、小账户纪律、团队/组合风险。
- [E01](experts-e01.md)：交互与零售投资产品。
- [E02](experts-e02.md)：量化与金融决策产品。
- [E03](experts-e03.md)：平台与模块联动产品。
- [代码审查](code-audit.md)和[15份源文件指纹](code-audit-manifest.json)：基线提交4dc61699a108bcdea4047c7df3acef7b9bd1b9da。
- [评审前工作提案](working-proposal.md)：仅保留推导过程，最终结论以redesign-plan.md为准。

## 已核验与未实施

离线原型完成7组交互检查和10组页面/宽度布局检查：同一上下文流转、超预算和未保存修改、数据过时与恢复、合约换月、视图切换、桌面/手机布局、无HTTP请求/脚本错误。结果在[原型QA记录](../../../output/product-redesign-2026-11-07/prototype-qa.json)。这不是生产验收或真实用户可用性验证。

报告已逐页渲染检查；原型有桌面及手机截图。完整交付指纹见[delivery-manifest.json](../../../output/product-redesign-2026-11-07/delivery-manifest.json)。未修改生产代码、模型参数、菜单权限、数据库、模拟会话或定时任务；未部署产品改版。

复现：安装reportlab、pypdf、Pillow后运行`scripts/build_product_redesign_report.py`（使用微软雅黑字体）；原型QA运行`scripts/qa_product_redesign_prototype.cjs`，需要Playwright和Edge，可通过PLAYWRIGHT_MODULE、PROTOTYPE_BROWSER指定本机路径。生成报告会将视觉检查标记重置为PENDING，必须重新渲染检查后才可交付。
