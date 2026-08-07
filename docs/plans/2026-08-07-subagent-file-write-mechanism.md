# Subagent 寫檔機制 — 根因與修法

日期：2026-08-07
版本：1.2.0
範圍：Day Subagent 與 Code Analysis Subagent 交付結果的寫檔機制。契約文字變更，
外加一支 prose 回歸測試與一個新的失敗回覆值。CLI 介面與 `.git-worklog/` layout 不變。

本文件分兩節：**§1–§6 是修法提案**（動工前寫），**§7 是實測記錄**（動工後補）。
兩節放在一起，是為了讓提案裡被推翻的判斷與推翻它的實測留在同一份文件內——
本次調查最大的成本，就花在一份根因寫錯的文件上。

---

## 1. 現象

2026-08-07，`/git-worklog` 對 `sr_ios` 生成當日日誌，連續三次派工失敗，
`analyze collect` 每次都回報 `missing` / `partial_run: true`。

| 次 | 模型 | 工具呼叫數 | 最後一筆記錄 | Write 內容長度 |
|---|---|---|---|---|
| 1 | Claude Haiku 4.5 | 14 | `Write` → `results/2026-08-07.json` | 15,600 字元 |
| 2 | Claude Haiku 4.5 | 11 | `Write` → 同路徑 | 13,585 字元 |
| 3 | Claude Sonnet 5 | 28 | `Write` → 同路徑 | 15,629 字元 |

三次都完整送出了帶著 JSON 的 Write 呼叫，之後 transcript 直接結束，沒有任何
tool_result。工具呼叫數 11 / 14 / 28 差異極大卻都停在唯一一個 Write，可排除回合
上限、token 預算與 context 用盡。同一批 subagent 的 Bash（`git show` 執行十餘次）
與 Read 全程正常。

**這不是 08-07 才開始的。** 前一天 08-06 的 session（`3e0e2a61`）同樣中招，只是當時
沒被辨認出來：

| row | 呼叫 | 結果 |
|---|---|---|
| 30 / 37 / 51 | `Write` → `results/2026-08-06.json` | 無 tool_result |
| 58 | `Write` → session scratchpad | 無 tool_result |
| 65 | `Bash` `cat > … <<'JSON'` | exit 0 |
| 68 | `ls -l` 驗證 | 7.1K ✓ |

08-06 那天之所以「成功」，是 subagent 自己臨場放棄 Write、改用 Bash quoted heredoc
換來的——連 delimiter 加引號都與本文件的修法一致。那一天的 42 KB 結果檔
（`rw-20260806-e56282/results/2026-07-22.json`，heredoc 命令字串 27,873 字元）
是目前最強的機制實證。

---

## 2. 根因

**subagent 發出的 Write tool call 會憑空消失：沒有 tool_result、沒有錯誤、沒有寫檔，
而且在該 agent 的下一個 turn 裡，那次呼叫不存在。**

最後一句是探針 E 才問出來的，也是整件事最關鍵的性質。追問該 agent「STEP 2 的 Write
回傳了什麼」，它的回答是「I have not yet executed STEP 2 — I only ran STEP 1」。
它感知到的不是「呼叫沒有回應」，而是「這一步我還沒做」。

### 2.1 探針

| 探針 | 機制 | payload 傳遞 | 大小 | 結果 |
|---|---|---|---|---|
| A | Write 工具 | inline | 11 B | ✗ 家目錄／scratchpad／專案內皆失敗 |
| B | Write 工具 | inline | 12.8 KB | ✗ 同上 |
| C | Bash（`printf`／`python3 -c`） | 執行時產生 | 15.3 KB | ✓ |
| D | Bash quoted heredoc | **inline** | 28.6 KB | ✓ 反引號未被當命令替換、`$` 未展開、反斜線與跳脫引號原樣保留 |
| E | Write 工具 **＋ `permissions.allow` 已授權該路徑** | inline | 21 B | ✗ 同一 agent 內連續失敗兩次 |
| F | Bash quoted heredoc | inline | 20.5 KB / 19.2 KB | ✓ 皆為有效 JSON |

各探針排除的假設：

- **A** 排除「只有專案外路徑被擋」：專案內 `<repo>/.git-worklog/` 同樣失敗。
- **A** 排除「payload 過大」：11 bytes 亦失敗。
- **C** 證明 Bash 可寫入該路徑，但大檔由 `python3 -c` 在執行時產生，命令字串本身很短，
  **未證明大 payload 能穿過 Bash 呼叫**。
- **D** 補上該缺口：28.6 KB 直接寫在單一 Bash 呼叫的 quoted heredoc 內。
- **E** 排除權限假設（見 §3）。
- **F** 未能量到傳輸上限，而失敗的方式本身就是結論（見 §4.5）。

### 2.2 證據涵蓋面

4 個 session（`3e0e2a61`／`a744941c`／`9ea0035c` 及探針各次派工）、2 種派工模式
（具名 agent 與 async 背景 agent）、3 種模型（Haiku 4.5／Sonnet 5／Haiku 4.5）、
3 類路徑（家目錄／session scratchpad／專案內）、有無 `permissions.allow` 規則、
同一 agent 內重複兩次。主執行緒的 Write 全程正常。

### 2.3 這個性質的兩個後果

1. **subagent 無法自我偵測。** 由於下一個 turn 裡那次呼叫不存在，任何形如
   「Write 若無回應則不得視為成功」的契約條款都不可能被觸發——沒有「無回應」這個
   狀態可供判斷。
2. **「先試 Write、失敗再退回 Bash」不可行。** 08-06 那個 subagent 能自救，是因為
   它在後續 turn 裡重新想起還沒寫檔而換了工具，不是因為它偵測到失敗。同樣情況在
   08-07 的三次派工中，agent 直接停在該處。這條路徑靠運氣。

---

## 3. 已排除的假設（修正版）

本文件曾有一版把根因判為「專案外路徑需要權限決定」，並據此寫成三套方案。以下修正
排除理由，避免日後依錯誤的推論重提。

| 假設 | 排除理由 |
|---|---|
| 授權 `~/.git-worklog` 至 `permissions.additionalDirectories` | `additionalDirectories` 只擴張工作區邊界，不等於授權寫入。它本來就不會修好這件事，但這與「是不是權限問題」無關。 |
| 狀態目錄搬進專案內 `.git-worklog/` 並 gitignore | 與路徑無關——探針 A 顯示專案內 `<repo>/.git-worklog/` 同樣失敗。另有獨立的不採用理由：執行狀態本質上是暫存，日誌完成後即無利用價值，不值得付出進版控的代價（`git clean -xdf` 會清光、目錄無自動清理、不看 gitignore 的搜尋會被污染、設定值只能寫絕對路徑導致無法團隊共用）。 |
| 降級改用 session scratchpad | 同上；scratchpad 寫入亦失敗（08-06 row 58、探針 A）。 |
| **「權限」整個方向** | **舊版以「專案內也失敗」反證權限，該推論無效**——在 `defaultMode: auto` 下專案內的 Write 一樣需要授權，所以那個觀察不排除任何東西。真正的排除來自探針 E：在 `permissions.allow` 加入該路徑的三種語法變體後重跑，Write 仍然消失兩次，同 turn 的 Bash 正常。補強論證有二：Agent 工具規格說 subagent 繼承 parent session 的 permission mode，而該 session 主執行緒的 Write／Edit 全程未被擋；且若是卡在等待授權，agent 會保持存活，實際上它是停止動作轉為 idle。 |

---

## 4. 修法

契約目前只說「a file write」，未指定機制，subagent 因而自然選用 Write 工具。修法是
把機制寫死。

### 4.1 機制：Bash quoted heredoc

```
cat > <result_path> <<'JSON_EOF'
{ …結果 JSON… }
JSON_EOF
```

選它而非 `python3 - <<'PY'`（寫入即驗證）或分塊 append 的理由：它是唯一有真實實證
的做法——08-06 的 subagent 在無人指導的情況下自行採用，27,873 字元命令字串、
產出 42 KB 有效 JSON、exit 0。

三項必須寫進 prompt 的細節，缺一即失敗：

1. **分隔符必須加引號**（`<<'JSON_EOF'`）。結果 JSON 的 prose 依 skill 規定大量使用
   反引號標記程式碼符號；未加引號的 heredoc 會把反引號當成命令替換執行，`$` 亦會被
   展開。這是必然發生的錯誤，非邊界情況。
2. **分隔符必須不與內容衝突。**
3. **分隔符必須在行首**（column 0），不得縮排。

### 4.2 契約措辭：明文禁用 Write

不只寫「MUST 用 heredoc」，要同時寫「MUST NOT 用 Write 工具」並附一行理由。理由與
規則寫在一起，才擋得住模型「試一下應該沒事」的直覺——08-06 那個 subagent 白燒了
四個回合在無回應的 Write 上。

§2.3 已說明：保留 Write 作為備援的寫法在物理上無法執行，不列入選項。

### 4.3 自我驗證與失敗協定

寫完必須在同一個 subagent 內驗證：

```
python3 -c "import json;json.load(open('<result_path>'))"
```

驗證失敗時重寫一次；仍失敗則回覆 `FAILED:<date>`（原本只能回 `DONE`）。

`FAILED` **不新增 orchestrator 行為**，§11 的失敗處理維持原樣：`collect` 仍是唯一
判定者，該日落入 `missing`、整個 run 標記 `partial_run`、apply 被擋。`FAILED` 的作用
只是讓 orchestrator 早一步知道，並且不得把該日當成空日子。

### 4.4 診斷步驟

`collect` 回報 `missing` 時，SKILL.md 的失敗處理段要給**可執行**的步驟。不能寫
「確認 subagent 是否用了 Write」——orchestrator 看不到 subagent 的 transcript，那句
無法執行。改寫為：`missing` 且 `result_path` 不存在時，重派該日並在 prompt 中重申
heredoc 機制。

現行機制其實已經攔得住這個問題（`collect` 回報 `missing`、`preview` 以
`RUN_NOT_COLLECTED` 拒絕，不會產出錯誤內容）。真正的缺陷是失敗時沒有任何線索指向
原因，導致本次連續四輪重跑（含一次模型升級）全部打在錯的方向。

### 4.5 為什麼不設 payload 上限

探針 F 原意是量出 heredoc 的傳輸上限，目標 48 KB 與 96 KB，實際只產出 20.5 KB 與
19.2 KB——第二個 rung 甚至比第一個小。卡住的不是傳輸，是**模型不願意把那麼長的
字面內容打出來**。

這個結果比量到數字更有用：payload 大小的瓶頸在模型輸出，而該限制對 Write 工具
**一視同仁**（Write 的 `content` 參數同樣得整包打出來）。所以改用 heredoc 並未讓大
payload 變得更難，「上限」不是這次修法引入的風險。既有的 `LARGE_DAY` 警告
（SKILL.md）已經是大日子的閘門，不再另設數字。

### 4.6 不做的事

- **canary／事前探測**：採用 heredoc 後不再是必要條件。若未來要加，設計必須符合
  兩點：由 subagent 執行（主執行緒寫得進去，測了是假綠燈），且探測實際使用的機制。
- **`~/.git-worklog/environment.json` 狀態記錄**：直接捨棄。它是為了記住一個權限決定
  而設計的，而該權限問題並不存在。
- **`prune` 指令**：狀態目錄的成長改為在 README 說明，由使用者自行決定何時清除。

---

## 5. 改動清單

| 檔案 | 內容 |
|---|---|
| `git-worklog/references/subagent-contract.md` | §6a 寫檔機制；§9 Day Subagent prompt 模板；§10 Code Analysis Subagent prompt 模板；§11 加一句「收到 `FAILED` 不得把該日當成空日子」 |
| `git-worklog/SKILL.md` | §3c 寫檔機制；失敗處理段的可執行診斷步驟 |
| `git-worklog/git_worklog/__init__.py` | `__version__` 1.1.0 → 1.2.0 |
| `tests/`（新檔） | prose 回歸測試：兩份 prompt 模板都含引號 delimiter 的 heredoc 指令，且不再出現 Write 工具的寫法 |
| `README.md` | 新增 State directory／狀態目錄小節（雙語） |
| `CHANGELOG.md` | 1.2.0 條目 |

版本定為 **1.2.0**（minor）：subagent 回覆協定新增了 `FAILED` 這個值，對任何讀契約
的人來說是介面變更。

### 5.1 部署

skill 從 `~/.claude/skills/git-worklog`（symlink → `~/.skillpod/skills/git-worklog`）
載入，而非從 repo。該處是實體副本，由 `skillpod` 管理，**skill 更新或重新安裝會覆蓋
本機手改**。修法必須進 repo，本機才透過同步生效。

---

## 6. 仍未驗證

- **`settings.json` 是否會在 session 中途重讀。** 探針 E 的 allow 規則是在該 session
  已啟動後才加入的；若設定不會中途重讀，探針 E 對權限假設的排除力就要打折。其餘
  三項補強論證（繼承 parent permission mode、主執行緒未被擋、等待授權會保持存活）
  不受此影響。
- **heredoc 的真實傳輸上限。** 量不到，原因見 §4.5。已知能通過的最大真實 payload 是
  27,873 字元命令字串。
- **此現象的適用範圍。** 無法判斷 subagent 的 Write 失效是此 Claude Code 版本的通病、
  本機特例，或暫時性狀況。確認方式：於另一個專案開新 session，重跑探針 A。若為通病，
  向 Claude Code 回報的價值高於修改 git-worklog——任何要求 subagent 產出檔案的 skill
  都會中招。
- **探針 A／B／E 的失敗未讀到明文拒絕訊息**，結論由「tool_result 缺席」「磁碟上檔案
  不存在」「agent 自述未執行該步」三者推得。

### 6.1 給 Claude Code 的最小重現（草稿，尚未送出）

> 派一個 subagent，要求它用 Write 工具寫入任何路徑、內容 11 bytes。該 tool call 不會
> 得到 tool_result、不會寫檔、不會報錯；agent 的下一個 turn 會表現得像那次呼叫從未
> 發生。同一 agent 內的 Bash 正常。與路徑、payload 大小、模型、派工模式、
> `permissions.allow` 是否涵蓋該路徑皆無關。主執行緒的 Write 不受影響。

---

## 7. 實測記錄

修法在本 repo 的 **2026-07-18**（7 個 commit、9 個檔案、6 組，`large_day: false`）上做了
前後對照。刻意用同一天、同一個 `run_id`、同一份 manifest、同一個 `result_path`、同一個
模型（Claude Haiku 4.5），**唯一變數是 prompt**。

`run_id: rw-20260807-1fb3b2`，語言 `zh-TW`（`agent-host`）。

### 7.1 對照組 — 現況契約

依當時的 §9 模板逐字派工，未做任何修改。

| 觀察點 | 結果 |
|---|---|
| subagent transcript | 38 rows：`Read` ×2、`Bash` ×9（`git show` 全部正常）→ 最後一筆是 `Write` → transcript 就此結束 |
| `results/2026-07-18.json` | 不存在 |
| `analyze collect` | `missing: ["2026-07-18"]`、`failed_dates: ["2026-07-18"]`、`partial_run: true` |

這是本次調查第一次讓該現象走完整條 pipeline，而不只是機制探針。

### 7.2 驗證組 — 新契約

同一份 manifest，改用新的 §9 模板重派。

| row | 事件 |
|---|---|
| 40 | `Bash` heredoc，**14,025 字元**命令 → 寫檔 |
| 43 | `python3 -c "import json;json.load(open(...))"` 自我驗證 |
| 46–47 | `ls -lh` → 17.9 KB、406 行 |
| 49 | 回覆 `DONE` |

**`Write` 工具呼叫次數：0。**

`analyze collect` 的判定從 `missing` 變成 `invalid`——**檔案送達了**。這正是要證明的那一步，
寫檔機制的修法在真實 pipeline 上成立。

### 7.3 分析品質是另一回事

驗證組雖然寫檔成功，那一天仍然沒過，原因與寫檔無關：

- `evidence[0]` 引用 `module_docstring`，`worktree.py@d6f6687` 沒有這個符號——正是 §8
  警告的捏造（`module_docstring` 是對符號的描述，不是符號）
- 三筆 `evidence` 缺必填的 `file` 鍵
- 另一筆把 `'new file'` 當成符號引用

依 §11「修分析，不修結果檔」，用同一份 manifest 重派一次並在 prompt 中點名這三項，
第二次 `collect` 得到 `complete: ["2026-07-18"]`、`partial_run: false`、`language: zh-TW`。

這個插曲值得記下來，因為它把兩種失敗模式乾淨地分開了：`missing` 是**檔案沒送達**（機制
問題，本次修法的對象），`invalid` 是**內容沒通過檢查**（分析品質問題，既有機制正常運作）。
先前的事故之所以難查，正是因為兩者都只呈現為「日誌沒生出來」。

### 7.4 走完 preview → apply

`preview` 產出 `rw-20260807-25923a`：`create` `.git-worklog/days/2026-07-18.md`、
`rebuild` `index.md`、`not_written: []`。確認後 `apply` 回報
`written_dates: ["2026-07-18"]`、`index_action: rebuild`、無 `mismatches`；
`validate` 回 `ok: true`；`coverage` 的 2026-07-18 從 `gap` 轉為 `covered`。

至此 prepare → 派工 → collect → preview → apply 全程在新契約下走通，補上了提案階段
「未以真實流程實測」那條缺口。**2026-07-27 仍是缺口**，本次未處理。

### 7.5 §6 的哪幾項假設被實測推翻

| 提案階段的說法 | 實測結果 |
|---|---|
| 「僅有單一 session 的資料」 | 錯。08-06、08-07 兩個 session，加上探針與本次前後對照共 4 個 session。 |
| 「Write 之後 transcript 直接結束」是必然 | 不是。08-06 的 subagent 吃了四次無回應的 Write 仍繼續執行。是否存活取決於模型行為。 |
| 權限假設「已被專案內也失敗排除」 | 該推論無效，但結論仍成立——探針 E 以 `permissions.allow` 實測排除（見 §3）。 |
| 需要先量出 heredoc 傳輸上限 | 量不到，而且不需要。瓶頸是模型輸出，對 Write 一視同仁（§4.5）。 |
