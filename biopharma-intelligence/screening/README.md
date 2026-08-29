# ASReview智能筛选使用说明

这个目录把GitHub自动收集的候选证据转成ASReview LAB 3可以直接读取的CSV。ASReview不会替你判断文章是否正确；它会学习你对“值得深入学习”的定义，并优先展示相似记录。

## 你每周需要做什么

1. 在GitHub中打开`biopharma-intelligence/screening/asreview_input.csv`。
2. 点击右侧下载按钮，保存CSV。
3. 打开[ASReview LAB在线版](https://asreview.app/)；也可以在电脑安装后本地运行。
4. 创建Review项目并上传`asreview_input.csv`。
5. 初始阶段至少标记一篇相关和一篇不相关记录，建议第一轮标记20条。
6. 后续每周只需筛选10至20条高优先级推荐。

## 相关/不相关的定义

点击`Relevant`，当记录符合至少一项：

- 关键II期或III期临床结果
- 监管批准或可能改变治疗路径的证据
- 新靶点、新技术首次出现人体概念验证
- 重要失败项目及可分析的失败原因
- 患者选择、biomarker、终点或试验设计具有学习价值
- 对CRA或临床运营有明确启发

点击`Irrelevant`，当记录主要属于：

- 与创新药开发关系较弱的基础研究
- 没有新数据的重复性综述或观点文章
- 仅提到疾病名称但研究核心无关
- 病例报告、低信息量描述或营销性内容
- 当前阶段不想深入的主题

不要把“阴性研究”自动标为不相关。失败和终止项目可能具有很高的学习价值。

## 推荐标签

在ASReview中可以建立以下标签：

- `deep-dive`：需要深入学习
- `watch`：持续观察
- `clinical-design`：试验设计值得研究
- `mechanism`：机制或技术平台
- `negative-result`：阴性或终止项目
- `CRA-operations`：与执行风险相关
- `low-evidence`：证据等级较低

## 如何在Codex中继续学习

筛选完成后，可以在这里提出：

> 读取我本周ASReview筛选后标记为相关的记录，按临床意义排序，并选择三条生成临床证据卡。

ASReview负责排序，Codex负责回到原始来源核查并解释。AI摘要不能替代论文全文、正式监管文件或人工临床判断。

## 本地安装（可选）

需要Python 3.10或更高版本：

```bash
pip install asreview
asreview lab
```

浏览器会打开本地ASReview界面。项目和标签自动保存在`.asreview`项目文件中；如需跨电脑继续，可导出该项目文件自行保存。
