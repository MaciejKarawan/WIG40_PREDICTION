from pathlib import Path
import unittest
import pandas as pd
from mwig_replication import config
from mwig_replication.ranking import compute_turnover_12m
class ProjectTests(unittest.TestCase):
    def test_data_paths_still_resolve_from_root(self):
        root=Path(__file__).resolve().parents[1]
        self.assertEqual(config.PROJECT_ROOT,root)
        self.assertEqual(config.INDEX_PORTFOLIOS_PATH,root/'output/wig_history/index_portfolios.parquet')
    def test_turnover_fixture(self):
        prices=pd.DataFrame({'isin':['A','A','B'],'date':pd.to_datetime(['2026-01-01','2026-01-02','2026-01-02']).date,'close':[2,3,4],'volume':[10,20,5]})
        result=compute_turnover_12m(prices,'2026-01-02').set_index('isin')
        self.assertEqual(result.loc['A','turnover_12m_pln'],80)
        self.assertEqual(result.loc['B','turnover_12m_pln'],20)
if __name__ == '__main__':unittest.main()
