with open('margo_server.py', 'r') as f:
    c = f.read()

old = """        # Remove palavras soltas comuns
        for w in ["tem","tem ","acha","ache","encontra","encontre","busca","busque","procura","procure",
                   "onde","qual","cadê","cade","um","uma","o","a","de","do","da","me","eu","quero",
                   "por","aqui","favor","find","search","look","for","the","a","an","i","want","need",
                   "can","you","is","there","any","some","good","best","onde fica","where is"]:
            query_raw = query_raw.replace(w, '')
        query_raw = ' '.join(query_raw.split()).strip()"""

new = """        # Remove palavras soltas comuns (apenas palavras inteiras, não partes)
        import re as _re2
        _stopwords = {"tem","acha","ache","encontra","encontre","busca","busque","procura","procure",
                      "onde","qual","cade","um","uma","me","eu","quero","por","favor",
                      "find","search","look","for","the","an","want","need",
                      "can","you","is","there","any","some","good","best"}
        palavras = query_raw.split()
        palavras = [p for p in palavras if p.lower() not in _stopwords]
        query_raw = ' '.join(palavras).strip()"""

if old in c:
    c = c.replace(old, new)
    with open('margo_server.py', 'w') as f:
        f.write(c)
    print('OK - stopwords corrigido para palavras inteiras')
else:
    print('ERRO - bloco nao encontrado')
