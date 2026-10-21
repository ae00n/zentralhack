from data_pipeline.embed import RRF_K, fuse


def test_rrf_prefers_consensus_over_single_top_hit():
    out = fuse([["a", "b", "c"], ["b", "c", "a"], ["b", "a", "d"]], k=3)
    assert [pid for pid, _ in out] == ["b", "a", "c"]
    assert abs(out[0][1] - (1 / (RRF_K + 2) + 2 / (RRF_K + 1))) < 1e-12


def test_rrf_truncates_to_k():
    assert len(fuse([["a", "b", "c", "d"]], k=2)) == 2
