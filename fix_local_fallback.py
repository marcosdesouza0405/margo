with open('margo_server.py', 'r') as f:
    c = f.read()

old = """    if found_type and (any(k in msg for k in local_kw) or any(k in msg for k in ["acha","ache","encontra","encontre","busca","busque","procura","procure","tem ","onde","qual","cadê","cade"])):
        import re as _re"""

new = """    # FALLBACK: se não achou tipo conhecido MAS tem indicador de localização,
    # manda pro maps_search com o texto bruto — Brave resolve nomes/marcas/erros
    if not found_type and any(k in msg for k in local_kw):
        import re as _re
        # Remove indicadores de local pra ficar só o nome do lugar
        query_raw = msg
        for kw in local_kw:
            query_raw = query_raw.replace(kw, '')
        # Remove palavras soltas comuns
        for w in ["tem","tem ","acha","ache","encontra","encontre","busca","busque","procura","procure",
                   "onde","qual","cadê","cade","um","uma","o","a","de","do","da","me","eu","quero",
                   "por","aqui","favor","find","search","look","for","the","a","an","i","want","need",
                   "can","you","is","there","any","some","good","best","onde fica","where is"]:
            query_raw = query_raw.replace(w, '')
        query_raw = ' '.join(query_raw.split()).strip()
        if query_raw:
            return {"ferramenta": "maps_search", "query": query_raw, "query_en": query_raw}

    if found_type and (any(k in msg for k in local_kw) or any(k in msg for k in ["acha","ache","encontra","encontre","busca","busque","procura","procure","tem ","onde","qual","cadê","cade"])):
        import re as _re"""

if old in c:
    c = c.replace(old, new)
    with open('margo_server.py', 'w') as f:
        f.write(c)
    print('OK - fallback para nomes desconhecidos adicionado')
else:
    print('ERRO - bloco nao encontrado')
