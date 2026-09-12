with open('margo_server.py', 'r') as f:
    c = f.read()

old = """    if found_type and (any(k in msg for k in local_kw) or any(k in msg for k in ["acha","ache","encontra","encontre","busca","busque","procura","procure","tem ","onde","qual","cadê","cade"])):
        # Extrai adjetivo/tipo (ex: "restaurante indiano" → "indian restaurant")
        import re as _re
        # Pega palavra depois do tipo (ex: "brasileiro", "indiano", "japonês")
        # Pega palavra depois do tipo (ex: "restaurante indiano")
        adj_match = _re.search(found_type + r'\\s+(\\w+)', msg)
        adj = adj_match.group(1) if adj_match else ""
        # Se não achou depois, pega palavra antes do tipo (ex: "indian restaurant", "sushi bar")
        if not adj:
            before_match = _re.search(r'(\\w+)\\s+' + found_type, msg)
            if before_match:
                adj = before_match.group(1)
        # Traduz adjetivos comuns
        _adj_trad = {"brasileiro":"brazilian","indiano":"indian","japonês":"japanese","japones":"japanese",
                     "italiano":"italian","chinês":"chinese","chines":"chinese","mexicano":"mexican",
                     "coreano":"korean","tailandês":"thai","tailandes":"thai","árabe":"arabic",
                     "arabe":"arabic","peruano":"peruvian","francês":"french","frances":"french",
                     "americano":"american","vegano":"vegan","vegetariano":"vegetarian"}
        _ignore = ["aqui","perto","de","do","da","em","no","na","um","uma","mim","me","mais","nearby","near","around","close","find","search","look","for","a","the","any","some","good",
                   "pra","pro","por","vez","pertinho","proximo","próximo","la","lá","outro","outra"]
        if adj.lower() in _ignore:
            adj = ""
        adj_en = _adj_trad.get(adj.lower(), adj) if adj else ""
        query_pt = f"{found_type} {adj}".strip() if adj else found_type
        query_en = f"{adj_en} {found_en}".strip() if adj_en else found_en
        return {"ferramenta": "maps_search", "query": query_pt, "query_en": query_en}"""

new = """    if found_type and (any(k in msg for k in local_kw) or any(k in msg for k in ["acha","ache","encontra","encontre","busca","busque","procura","procure","tem ","onde","qual","cadê","cade"])):
        import re as _re
        _ignore = ["aqui","perto","de","do","da","em","no","na","um","uma","mim","me","mais",
                   "nearby","near","around","close","find","search","look","for","a","the",
                   "any","some","good","pra","pro","por","vez","pertinho","proximo","próximo",
                   "la","lá","outro","outra","bom","boa","melhor","best","have","is","there",
                   "tem","onde","qual","cadê","cade","acha","ache","encontra","encontre",
                   "busca","busque","procura","procure","i","want","need","can","you"]
        # Verifica se tem palavras relevantes antes ou depois do tipo
        before_match = _re.search(r'(\\w+)\\s+' + _re.escape(found_type), msg)
        after_match = _re.search(_re.escape(found_type) + r'\\s+(\\w+)', msg)
        before_word = before_match.group(1).lower() if before_match else ""
        after_word = after_match.group(1).lower() if after_match else ""
        # Se tem adjetivo/qualificador relevante, deixa a IA interpretar
        if (before_word and before_word not in _ignore) or (after_word and after_word not in _ignore):
            pass  # Não retorna — IA resolve com mais contexto
        else:
            # Tipo simples sem qualificador — pré-detector resolve direto
            return {"ferramenta": "maps_search", "query": found_type, "query_en": found_en}"""

if old in c:
    c = c.replace(old, new)
    with open('margo_server.py', 'w') as f:
        f.write(c)
    print('OK - pre-detector simplificado')
else:
    print('ERRO - bloco nao encontrado')
