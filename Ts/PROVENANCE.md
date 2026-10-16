# Ts 绘图模块来源

来源：[BichengNiu/Ts](https://github.com/BichengNiu/Ts)，固定提交 `167ec2a133608640ecb2d89925902cafb32daee5`（2026-10-16 读取）。

复用其公共 `plot_series` API；检索了 `TsPlots/README.md`、`TsPlots/__init__.py` 及 `TsPlots/ts_plot.py`。总量和多船型叠加图直接调用该接口，未复制绘图算法形成新实现。

仅内置原始 `TsPlots/ts_plot.py`、`TsPlots/style.py`、`TsPlots/bar_plot.py` 和依赖的 `TsUtils/_validation.py`，内容未经修改。适配入口 `Ts/TsPlots/__init__.py` 只导出 `plot_series`，其他目录入口不导入无关模块。完整 Ts 的安装元数据要求 Python >=3.13 和统计建模依赖；本应用仅使用绘图模块，已验证 Python 3.12、requirements.txt 中的绘图依赖，不声明完整 Ts 的兼容性。上游未提供 LICENSE 文件；本次依用户指定其本人仓库的指示使用，保留所有源文件和来源。

- `TsPlots/ts_plot.py` SHA-256: `a3029308e174048cbceda8be621f092598d3853f10891a70adee6496d6bc6e09`
- `TsPlots/style.py` SHA-256: `f00abfbd73f9de3d68f44e08b7ff2b20637fdbb944125dae91b670e9ac884968`
- `TsPlots/bar_plot.py` SHA-256: `82f892725d8181d4c429482c8ecca191dcacaa3d6c0dceb829b5163c6c3e3d68`
- `TsUtils/_validation.py` SHA-256: `87959f969041d3e4d9de5664475dd5f483c419dacc3e9bed40bed64ce75ecf66`
