# Auto YOLO Training · 数据集约定与转换

> 本项目支持三种输入数据集格式：**YOLO 检测格式**（直接训练）/ **分类格式**（自动转换）/ **Roboflow 导出格式**（自动识别）。

---

## 1. YOLO 检测格式（首选）

### 目录结构

```text
dataset/my-dataset/
├── data.yaml
├── images/
│   ├── train/
│   ├── val/
│   └── test/         # 可选
└── labels/
    ├── train/
    ├── val/
    └── test/
```

### `data.yaml`

```yaml
path: ../../dataset/my-dataset      # 可省略：Ultralytics 默认用 yaml 所在目录
train: images/train
val: images/val
test: images/test
nc: 2                               # 类别数
names: ['cat', 'dog']              # 类别名列表
```

### 标签格式

每个 `.jpg` 对应同名 `.txt`，每行：

```text
class_id x_center y_center width height
```

坐标与宽高归一化到 `0`~`1`。例如：

```text
0 0.5 0.5 0.2 0.3
1 0.3 0.7 0.1 0.2
```

---

## 2. 图像分类格式（自动转换）

`src.dataset_manager.AutoDatasetManager` 可识别并转换：

```text
dataset/my-classification/
├── train/
│   ├── cat/        # 子目录名 = 类别名
│   │   ├── img001.jpg
│   │   └── ...
│   └── dog/
└── val/
    ├── cat/
    └── dog/
```

转换后会生成 `dataset/my-classification-yolo/`：

```text
dataset/my-classification-yolo/
├── data.yaml        # 自动生成 nc=2, names=['cat', 'dog']
├── images/
└── labels/
```

### 转换用法

```python
from src.dataset_manager import AutoDatasetManager

manager = AutoDatasetManager("dataset")
# 单个数据集
result = manager.convert_dataset("my-classification", delete_original=False)
# 批量（默认 delete_original=False，阶段 A7 后）
results = manager.convert_all_datasets(delete_original=False)
```

> ⚠️ **重要（阶段 A7 设计变更）：** 转换默认 `delete_original=False`，原分类数据集**不会**被自动删除。如需删除，调用时显式传 `delete_original=True`。

---

## 3. Roboflow 导出格式

Roboflow 导出的 YOLO 格式自动识别（含 `data.yaml` 顶部注释）：

```yaml
# 自动生成的YOLO数据集配置
train: images/train
val: images/val
test: images/test
nc: 2
names: ['good', 'defect']
```

---

## 4. 验证数据集

### 命令行

```bash
# 人类可读输出
python validate_data.py my-dataset

# JSON 报告（便于脚本处理）
python validate_data.py my-dataset --json > report.json
```

### 校验内容

`src.data_validator.DataValidator` 检查 4 类：

| 检查项 | 说明 |
|---|---|
| **结构** | images/labels 目录、train/val/test split 存在 |
| **规模** | train ≥ 50、val ≥ 10、val/train ≥ 10% |
| **类别一致性** | data.yaml 声明的 nc 与实际标注一致 |
| **类别平衡** | train/val 各类别实例数失衡比 ≤ 10x |

---

## 5. 类别推断

`ConfigGenerator._infer_classes` 优先级：

1. **读 `data.yaml`**：若存在 `names` 与 `nc`，直接使用
2. **扫描标签**：遍历所有 `.txt`，收集实际出现的 class_id，最大值 + 1 = nc，名字用 `class_{i}` 占位
3. **失败抛错**：若既无 yaml 也无标签，抛 `ClassInferenceError`（阶段 A10 引入）

---

## 6. 项目当前数据集清单

| 数据集 | 类别数 | 图像数 (train/val/test) | 状态 |
|---|---:|---|---|
| `cabel-damage-mini` | 2 | 919 / 265 / 134 | ✅ 标签完整 |
| `data` | 2 | 296 / 75+0 / — | ⚠️ val 无标注，README 已声明 |
| `cable end sleeve-yolo` | 2 | 待检 | ⚠️ 命名带空格，路径易出 BUG |
| `ring cable lug-yolo` | 6 | 待检 | ✅ |
| `_smoke_test` | 1 | 2 / 2 / 0 | ✅ 仅用于烟雾测试 |

---

## 7. 故障排查

### 路径问题

```bash
# 验证 YAML 路径解析是否正确
python -c "
import yaml
with open('configs/models/data_my-dataset.yaml') as f:
    d = yaml.safe_load(f)
print('train:', d['train'])
import os
print('exists:', os.path.exists(d['train']))
"
```

### CRLF/LF 混用

`configs/*.yaml` 文件历史混合了 CRLF/LF。PyYAML 两种都支持，但 git 会按 `.gitattributes` 的 `* text=auto` 规范化。

### 类别不匹配

```bash
python validate_data.py my-dataset --json | python -c "
import json, sys
r = json.load(sys.stdin)
for issue in r['errors']:
    if 'class_mismatch' in issue['category']:
        print(issue)
"
```

---

## 8. 进阶

### 自定义类别名

编辑 `dataset/my-dataset/data.yaml`：

```yaml
names: ['正常', '缺陷', '严重缺陷']  # 支持中文（YAML UTF-8）
```

`ConfigGenerator` 读 yaml 时用 `allow_unicode=True`，中文标签在 Gradio 显示正常。

### 类别权重（不平衡数据）

通过训练覆盖参数：

```bash
python train.py my-dataset --override cls=1.5  # 提升分类损失权重
```

阶段 C 计划加入自动类别权重（基于 inverse frequency）。