import pandas as pd
from addr.cli import run

def test_run_writes_output(tmp_path):
    inp = tmp_path / "in.xlsx"
    out = tmp_path / "out.xlsx"
    pd.DataFrame({"名称": ["同仁堂国医馆"], "地址": [""]}).to_excel(inp, index=False)
    run(str(inp), str(out))
    df = pd.read_excel(out)
    assert "最终标准分类" in df.columns
    assert df.loc[0, "最终标准分类"] == "私人诊所"
