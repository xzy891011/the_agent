# 中文字体配置说明

## 问题描述

在Ubuntu系统上，matplotlib默认不支持中文字符显示，导致图表中的中文文字显示为方框。

## 解决方案

### 1. 自动检测和配置

系统已经自动配置了中文字体支持，会按以下优先级寻找可用字体：

1. **WenQuanYi Zen Hei** (文泉驿正黑) - ✅ 已确认可用
2. **WenQuanYi Micro Hei** (文泉驿微米黑)
3. **Noto Sans CJK SC** (Noto中文简体)
4. **SimHei** (黑体)
5. **Microsoft YaHei** (微软雅黑)
6. **DejaVu Sans** (备选字体)

### 2. 手动安装字体（如果需要）

如果系统没有中文字体，可以运行安装脚本：

```bash
# 给脚本添加执行权限
chmod +x install_chinese_fonts.sh

# 运行安装脚本（需要sudo权限）
./install_chinese_fonts.sh
```

或者手动安装：

```bash
# 更新包索引
sudo apt-get update

# 安装中文字体包
sudo apt-get install fonts-wqy-zenhei fonts-wqy-microhei fonts-noto-cjk
```

### 3. 清理字体缓存

安装新字体后需要清理matplotlib缓存：

```bash
# 删除字体缓存
rm -rf ~/.cache/matplotlib
rm -rf ~/.matplotlib

# 重建字体缓存（Python）
python -c "import matplotlib.font_manager as fm; fm.fontManager.addfont('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc')"
```

### 4. 验证字体配置

运行测试脚本验证字体是否正确配置：

```bash
python test_chinese_fonts.py
```

成功的输出应该包含：
- ✅ 找到 WenQuanYi Zen Hei 字体
- ✅ 无字符缺失警告
- ✅ 图表文件生成成功

## 技术实现

### 字体配置代码

两个主要的图表生成模块都已经配置了中文字体支持：

- `app/tools/isotope/enhanced_isotope_visualization.py`
- `app/tools/isotope/enhanced_isotope_depth_trends.py`

每个模块都包含 `setup_chinese_font()` 函数，会：

1. 自动检测系统可用字体
2. 按优先级选择最佳中文字体
3. 配置matplotlib使用选定字体
4. 验证字体是否真正支持中文
5. 提供详细的日志信息

### 关键配置参数

```python
plt.rcParams['font.sans-serif'] = ['WenQuanYi Zen Hei']  # 设置中文字体
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
```

## 常见问题

### Q: 图表中文仍显示为方框

**A:** 请尝试以下步骤：
1. 重启Python程序
2. 清除matplotlib缓存：`rm -rf ~/.cache/matplotlib`
3. 确保虚拟环境已激活：`conda activate sweet`
4. 运行字体测试：`python test_chinese_fonts.py`

### Q: 在Docker容器中如何配置

**A:** 在Dockerfile中添加：
```dockerfile
RUN apt-get update && apt-get install -y fonts-wqy-zenhei fonts-noto-cjk
```

### Q: 如何检查系统可用字体

**A:** 使用以下命令：
```bash
# 查看所有中文字体
fc-list :lang=zh-cn

# 查看文泉驿字体
fc-list | grep -i wqy
```

## 系统兼容性

- ✅ Ubuntu 20.04+
- ✅ Debian 10+
- ✅ Docker容器环境
- ✅ Conda虚拟环境

## 更新日志

- **2024-06-30**: 修复中文字体显示问题，配置WenQuanYi Zen Hei字体
- **2024-06-30**: 添加自动字体检测和验证功能
- **2024-06-30**: 创建字体安装脚本和测试工具

---

如果遇到其他字体相关问题，请检查系统日志或联系技术支持。 