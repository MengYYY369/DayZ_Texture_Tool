# DayZ Texture Tool

DayZ 贴图转换桌面工具。第一版是独立 Python 工具，不依赖 GameImageUtil 的 C# 运行时。

## 功能

- `Game2PBR`
  - 支持拖拽单张或多张图片。
  - 支持选择文件夹并按后缀自动处理。
  - 支持处理器：`SplitColorAlphaProcessor`、`SplitRGBAProcessor`、`MergeRGBAProcessor`、`XYNormalMapProcessor`、`DirectConvertProcessor`、`DirectinvertProcessor`、`DF_NRM`、`DF_MRA`、`ABI_ORN`。
  - `_NRM` 自动走 `DF_NRM`，`_MRA` 自动走 `DF_MRA`，`_ORN` 自动走 `ABI_ORN`。

- `PBR2DayZ`
  - 递归扫描文件夹，按文件名识别 BaseColor、Normal、Roughness、Metallic、AO。
  - 输出 `_co.tga`、`_nohq.tga`、`_smdi.tga`、`_as.tga` 到贴图所在目录。
  - 支持 DirectX/OpenGL normal、auto/固定分辨率。
  - 可选调用 `ImageToPAA.exe` 生成 PAA。

- `Settings`
  - 保存 `ImageToPAA.exe` 路径。
  - 支持中英文切换。

## 安装与运行

```powershell
python -m pip install -r requirements.txt
python -m pip install -e .
dayz-texture-tool
```

如果 `dayz-texture-tool` 不在 PATH，可以使用：

```powershell
python -m dayz_texture_tool
```

## 输出规则

- 默认输出到原图所在目录。
- `Game2PBR` 默认输出 `.png`。
- `PBR2DayZ` 输出 `.tga`。
- 除 `DF_MRA` 外，不删除源文件。
- `DF_MRA` 会删除原图和 `_a`，并将 `_r/_g/_b` 重命名为 `_met/_rou/_ao`。

## 测试

```powershell
python -m unittest discover -s tests
```
