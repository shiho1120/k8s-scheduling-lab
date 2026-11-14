# Kubernetes Resource-Aware Scheduler

使用 Python 實作自訂 Kubernetes Scheduler，透過 Prometheus 取得節點即時 CPU 與記憶體使用率，進行工作負載排程，並與 Kubernetes Default Scheduler 比較排程行為與效能。

## 功能

- **Pending Pod Detection**：偵測等待排程的 Pods。
- **Node Filtering**：根據 Pod Resource Requests 與節點可用資源篩選 Worker Nodes。
- **Resource-Aware Scoring**：利用 Prometheus 的 CPU、Memory 指標計算節點分數。
- **Pod Binding**：透過 Kubernetes API 將 Pod 指派至選定節點。
- **Batch Scheduling**：支援多個 Pods 的自動排程。
- **Performance Benchmark**：分析 Kubernetes API 查詢與 Scheduler 執行效能。

## 環境建置

使用 VMware 建立 Kubernetes Cluster，包含一台 Control Plane 與三台 Worker Nodes。

| 項目 | 環境 |
|---|---|
| 作業系統 | Ubuntu 24.04 LTS |
| Kubernetes | v1.35.9 |
| Cluster | 1 Control Plane + 3 Workers |
| Container Runtime | containerd |
| CNI | Calico |
| Monitoring | Prometheus / Grafana |
| 開發語言 | Python 3.12 |

## 排程機制

Scheduler 分為三個主要階段：

1. **Filtering**：檢查節點狀態、Pod 資源需求與剩餘可分配資源，篩選符合條件的 Worker Nodes。
2. **Scoring**：從 Prometheus 取得節點 CPU、Memory 使用率，計算各節點分數。
3. **Binding**：選擇分數最高的 Worker，透過 Kubernetes API 完成 Pod Binding。

目前使用的評分公式：

```text
Score = 0.6 × (1 - CPU Usage) + 0.4 × (1 - Memory Usage)
```

## 實驗結果

### 1. Default Scheduler vs Resource-Aware Scheduler

使用 CPU-intensive Jobs，比較一般負載與 CPU Pressure 情境下的排程表現。

| 指標 | Default Scheduler | Resource-Aware Scheduler |
|---|---:|---:|
| 一般負載平均排程等待 | 0 秒 | 1.33 秒 |
| CPU Pressure 平均排程等待 | 0 秒 | 2.33 秒 |

在 CPU Pressure 情境下，兩種 Scheduler 都避開高負載的 Worker1，自訂 Scheduler 則將測試 Jobs 集中排程至 Worker3。

### 2. Kubernetes API 效能最佳化

比較使用 `kubectl` 與 Kubernetes Raw API 進行 Node Filtering 的效能。

| 方法 | Filtering 中位數耗時 |
|---|---:|
| kubectl | 218.207 ms |
| Raw API | 23.807 ms |

在 20 輪 Benchmark 中，Raw API 的 Filtering 耗時降低約 **89.09%**。

此測試未包含 Python 程序啟動與首次模組載入成本。

### 3. 實際排程效能比較

將 Raw API 整合至 Batch Scheduler，測量實際排程成本，每組測試 3 個 CPU Jobs。

| 指標 | kubectl | Raw API |
|---|---:|---:|
| 平均 Filtering | 253.865 ms | 273.682 ms |
| 平均 Scheduler Total | 517.310 ms | 557.826 ms |
| 平均 Subprocess Duration | 575.662 ms | 671.385 ms |

雖然 Raw API 在獨立 Benchmark 中有明顯改善，但在目前的 Batch Scheduler 架構下，整體排程耗時並未降低。初步分析顯示，Python Client 首次載入與重複建立子程序的成本，是影響整體效能的因素之一。

以上為小規模實驗結果，尚未進行統計顯著性驗證。

## 專案結構

```text
scheduler/
├── pending_pod_scanner.py       # Pending Pod 偵測
├── node_filter.py               # 資源需求與節點過濾
├── integrated_scheduler.py      # Filtering 與 Scoring
├── resource_aware_scheduler.py  # Prometheus 資源指標查詢
├── schedule_once.py             # 單次排程與 Binding
├── batch_scheduler.py           # 批次自動排程
└── k8s_raw_client.py            # Kubernetes Raw API

experiments/                     # 測試工作負載與實驗設定
results/                         # 排程紀錄與效能測試結果
```

## 使用方式

需先準備 Kubernetes Cluster、kubeconfig，以及可連線的 Prometheus API。

### 1. 建立 Python 環境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install kubernetes==35.0.0
```

### 2. 執行 Scheduler Dry Run

```bash
python scheduler/integrated_scheduler.py
```

### 3. 使用 Kubernetes Raw API

```bash
SCHEDULER_API_SOURCE=raw python scheduler/integrated_scheduler.py
```

### 4. 執行 Filtering 效能測試

```bash
python scheduler/benchmark_filter_source.py
```
