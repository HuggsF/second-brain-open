from core.consulta_texto import expressao_match, termos


def test_termos_minusculos_sem_repeticao_e_sem_palavras_vazias():
    assert termos("Como o Hub trata a emissão da emissão?") == ["hub", "trata", "emissão"]


def test_termo_curto_fica_de_fora():
    assert termos("NF de ar") == []


def test_radical_so_em_termo_longo_sem_digito():
    assert expressao_match("emissões fila RULE-005 pb_013") == '"emissõ"* OR "fila" OR "rule" OR "005" OR "pb_013"'


def test_pergunta_so_com_palavras_vazias_devolve_none():
    assert expressao_match("como é que o de para") is None
    assert expressao_match("") is None


def test_sintaxe_do_fts_fica_inerte():
    for entrada in ['"', '*', 'NEAR(a b)', 'titulo:hub', '-hub', '(hub OR', 'hub OR']:
        saida = expressao_match(entrada)
        assert saida is None or all(parte.startswith('"') for parte in saida.split(" OR "))
        assert saida is None or '""' not in saida
        assert saida is None or not any(c in saida for c in "():-")


def test_aspas_internas_sao_removidas():
    assert expressao_match('hub"logistico') == '"hub" OR "logisti"*'
