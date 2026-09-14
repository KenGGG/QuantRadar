# G4 固定版本 ETF_RAW 回放

在 release `R9c1b6c13965dc457` 上以相同的 `ETF_RAW` 策略连续运行两次：
2021-01-04 至 2021-01-08，`159915.XSHE` 首日买入 100 份。

两次均绑定基础 commit `uhdpedb4pr97ve80aq6nrabr66atsqtq` 与补充 commit
`r4t6rm3fdtb06rqpk0bmbtp2hn638a5r`，结果指纹相同：

```
0020bceca29b4eba91dac37a58bb6e11ac570715ec2fb120ae7aa0802aa11fc
```

策略在 `initialize` 中显式设置 `current_bar_fq='none'`；回放只读取固定 Dolt 版本，
不进行网络请求。此验证证明 ETF_RAW 研究重放可复现，不改变 ETF 调整因子、公司行为或严格账户的
`BLOCKED` 状态。
