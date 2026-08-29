## 胃癌创新药跟踪器

当前MVP从两个公开数据源获取候选信息：

- PubMed：最近14天胃癌/胃食管结合部腺癌治疗相关文献
- ClinicalTrials.gov：相关干预性研究及其关键登记字段

### 手动运行

需要Python 3.10或以上版本，不需要安装第三方依赖：

```bash
python biopharma-intelligence/scripts/update_tracker.py
```

运行后生成：

- `biopharma-intelligence/data/publications.csv`
- `biopharma-intelligence/data/trials.csv`
- `biopharma-intelligence/data/trial_changes.json`
- `biopharma-intelligence/data/raw/`中的可追溯原始快照
- `biopharma-intelligence/weekly-reports/generated/YYYY-MM-DD.md`

首次运行时，全部试验会标记为`new`；第二次及以后才会识别状态、入组数、阶段、主要完成日期、干预措施和主要终点的变化。

### GitHub自动运行

工作流每周一08:20（北京时间）执行，也可以在Actions页面手动触发。建议在仓库的Actions secrets中配置：

- `NCBI_EMAIL`：NCBI请求联系邮箱
- `NCBI_API_KEY`：可选；提高NCBI API请求限额

自动生成的是“候选周报”，保留人工解读位置。标题或注册字段不足以支持疗效、安全性或项目成败判断，因此当前版本不会自动编造临床结论。
