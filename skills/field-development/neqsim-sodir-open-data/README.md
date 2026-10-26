# neqsim-sodir-open-data

Catalog and read-only client for the Sokkeldirektoratet (Sodir) open data. See [SKILL.md](SKILL.md).

```bash
pip install -e .
python -m sodir_open_data search wellbore formation top
python -m sodir_open_data describe wellbore_dst
python -m sodir_open_data usecase pvt
pytest
```

Data: Norwegian Offshore Directorate, NLOD 2.0. Pure standard library; no keys.
