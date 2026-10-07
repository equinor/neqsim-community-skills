# neqsim-ncs-ownership-equity

Who owns Norwegian Continental Shelf fields, discoveries and licences, read live
from the open Sodir DataService, plus the net-equity arithmetic that field
evaluation and economics need. Prospect equity is not public: enter it yourself
or use the licence it sits in as a labelled proxy.

## Quick Start

```powershell
C:\appl\neqsim-venv\Scripts\python.exe -m pip install -e ".[test]"
C:\appl\neqsim-venv\Scripts\python.exe -m pytest
```

```python
from ncs_ownership_equity import OwnershipReader
reader = OwnershipReader()
reader.field("Troll").fractions()
reader.discovery("Wisting").to_economics_handoff("Aker BP")
reader.portfolio("Aker BP ASA")["items"][:5]
```

- The reader takes an injectable `fetch(url, timeout) -> bytes`, so tests run offline.
- Every read is recorded in `reader.client.records` with layer, query and retrieval time.
- See [SKILL.md](SKILL.md) for the method, limits and hand-offs.
