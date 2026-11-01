| scenario   | metric          |   adaptive |   static |      diff |   n_adaptive |   n_static | significant   |
|:-----------|:----------------|-----------:|---------:|----------:|-------------:|-----------:|:--------------|
| none       | delivery_pct    |     100    |   100    |      0    |           15 |         15 | no            |
| none       | lat_p95_ms      |      50.24 |    48.32 |      1.91 |           15 |         15 | no            |
| none       | retransmissions |      22.2  |    11.4  |     10.8  |           15 |         15 | no            |
| linkdown   | delivery_pct    |     100    |    70.8  |     29.2  |           15 |         15 | yes           |
| linkdown   | recovery_ms     |     123.56 | 10173.8  | -10050.2  |           15 |         15 | yes           |
| linkdown   | lat_p95_ms      |      42.49 |   502.09 |   -459.6  |           15 |         15 | yes           |
| linkdown   | retransmissions |      16.93 |  2802.67 |  -2785.73 |           15 |         15 | yes           |
| blackhole  | delivery_pct    |     100    |    70.4  |     29.6  |           15 |         15 | yes           |
| blackhole  | recovery_ms     |     389.76 | 10319.8  |  -9930.03 |           15 |         15 | yes           |
| blackhole  | lat_p95_ms      |      53.8  |   457.12 |   -403.32 |           15 |         15 | yes           |
| blackhole  | retransmissions |      47    |  2808    |  -2761    |           15 |         15 | yes           |