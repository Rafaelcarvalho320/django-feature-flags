# django-feature-flags

[![CI](https://github.com/Rafaelcarvalho320/django-feature-flags/actions/workflows/ci.yml/badge.svg)](https://github.com/Rafaelcarvalho320/django-feature-flags/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)
[![Django](https://img.shields.io/badge/django-4.2%20%7C%205.x-092E20)](https://www.djangoproject.com/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Feature flags em banco para Django: liga e desliga pelo admin, rollout
percentual **pegajoso**, lista de usuários e grupos, janela de tempo,
decorator de view e tag de template. Uma dependência de runtime: o Django.

> *[English summary below](#english-summary)*

## Instalação

```bash
pip install git+https://github.com/Rafaelcarvalho320/django-feature-flags.git
```

```python
# settings.py
INSTALLED_APPS = [..., "feature_flags"]
```

```bash
python manage.py migrate
```

## Uso

```python
from feature_flags import flag_is_active, flag_required

if flag_is_active(request, "new-checkout"):
    ...


@flag_required("new-checkout")
def checkout(request): ...


@flag_required("new-checkout", redirect_to="/checkout/legacy/")
def checkout(request): ...
```

```django
{% load feature_flags %}

{% flag "new-checkout" as new_checkout %}
{% if new_checkout %}...{% endif %}

{% if "new-checkout"|flag_active:request %}...{% endif %}
```

Para código sem request na mão — um job noturno, um comando — existe
`flag_is_active_for_user(user, "new-checkout")`, que decide exatamente igual ao
que o usuário vê no navegador.

## O rollout é pegajoso

É o requisito que molda o projeto inteiro. Quem vê a feature às 10:00 tem que
continuar vendo às 10:01, e quem está dentro a 10% tem que continuar dentro a
11% — senão o rollout vira um piscar que faz a feature parecer quebrada e as
métricas não significarem nada.

Saída real de `in_rollout("new-checkout", ...)` para doze usuários:

```text
usuario:    1   2   3   4   5   6   7   8   9  10  11  12
   0%:      .   .   .   .   .   .   .   .   .   .   .   .
  10%:      .   x   .   .   .   .   .   .   .   .   .   .
  25%:      .   x   .   .   .   .   .   .   .   x   .   .
  50%:      .   x   .   .   .   x   .   .   .   x   x   x
 100%:      x   x   x   x   x   x   x   x   x   x   x   x
```

**Ninguém perde o `x` quando a porcentagem sobe.** Subir só adiciona, nunca
move alguém para fora — é isso que torna seguro aumentar um rollout, e é o que
um sorteio por requisição jamais poderia prometer. Tem teste varrendo 0 a 100
de 5 em 5 e exigindo que o conjunto só cresça.

O balde é **derivado**, não armazenado: `sha256(flag + ":" + user_pk) % 100`.
Guardar a atribuição por usuário por flag funcionaria, ao custo de uma tabela
que cresce com usuários × flags e precisa ser escrita na primeira visita.

Três detalhes que não são decoração:

- **`hash()` do Python está fora.** Ele é *salted* por processo para strings,
  então daria uma resposta diferente em cada worker e o usuário piscaria ao
  trocar de worker. É a única função que não serve aqui, e é a primeira que se
  pensa em usar.
- **O nome da flag entra no digest**, então quem foi azarado num rollout não é
  sistematicamente o primeiro de todos os outros.
- **Buckets por chave primária, não por username.** Renomear não pode mudar o
  balde de alguém no meio de um rollout.

## A ordem das regras

Avaliadas de cima para baixo, e documentada num só lugar no código:

| # | Regra | Resultado |
| --- | --- | --- |
| 1 | A flag não existe | **off** |
| 2 | `enabled` desligado | **off** |
| 3 | Fora da janela de tempo | **off** |
| 4 | `staff_only` e o usuário não é staff | **off** |
| 5 | Usuário na lista, ou em grupo permitido | **on** |
| 6 | Dentro da porcentagem | **on** |
| 7 | Caso contrário | **off** |

**Flag inexistente é off.** A alternativa é que apagar uma linha, ou um erro de
digitação no nome da flag, entregue uma feature pela metade para todo mundo.

**`staff_only` é um portão, não uma regra.** Estar na lista de permitidos não
passa um usuário não-staff por ele.

**A lista vem acima da porcentagem**, para o time ver a feature
independentemente de onde o balde caiu.

**Visitante anônimo é off abaixo de 100%.** Não há identidade estável para
bucketizar, e um sorteio daria respostas diferentes em carregamentos
consecutivos da mesma página. Bucketizar por chave de sessão foi considerado e
recusado: sessão que rotaciona move o usuário de balde, que é exatamente o
piscar que o desenho existe para evitar.

## O cache, e por que ele é a parte perigosa

Uma flag é lida em praticamente toda requisição, várias vezes no mesmo
template, e a linha quase nunca muda. Ler a tabela sempre é query comprada por
nada — mas cache de flag é também o jeito mais fácil de fazer um botão de
desligar que não desliga.

- **O conjunto todo num único key.** Uma página que checa seis flags custa uma
  leitura de cache, não seis, e limpar é um delete só, sem chance de meio
  conjunto velho.
- **Invalidação em `post_save` e `post_delete`.** O caminho rápido: mexer na
  flag tem efeito imediato.
- **Invalidação em `m2m_changed` também.** As listas de usuários e grupos são
  tabelas separadas, então salvar a flag não está envolvido. Sem esse receiver,
  adicionar alguém à lista não fazia nada até o timeout expirar — que se lê
  como a feature estando quebrada. Tem teste.
- **Timeout de 5 minutos como rede de segurança**, para o deployment
  multi-processo onde o sinal de um worker nunca chega ao cache do outro.
- **A ação em massa do admin salva uma linha por vez**, não com
  `queryset.update()`: um update em massa não emite `post_save`, então o cache
  continuaria respondendo o valor antigo e a ação pareceria não ter feito nada.
- **Memoização por requisição.** Um template que checa a mesma flag em três
  lugares não roda as queries da lista de permitidos três vezes.

## O admin

É o motivo de as flags viverem numa tabela e não no `settings`: um deploy não é
uma unidade aceitável de "desliga isso", e durante um incidente quem precisa do
botão raramente é quem pode subir código.

A coluna de estado traduz a configuração para uma frase — `on for everyone`,
`on: staff only, 25%`, `off (outside window)` — e a tela avisa quando uma flag
está habilitada mas ninguém a alcança, que é o erro mais fácil de cometer:
`enabled` ligado, porcentagem em zero, nenhuma lista.

## Testes

```bash
pip install -e ".[dev]"
pytest                  # 62 testes
ruff check . && ruff format --check .
mypy                    # strict, com django-stubs
```

A suíte usa `LocMemCache` de propósito, para exercitar o caminho real de cache:
"o toggle não fez nada porque o cache não foi limpo" é o bug que mais merece
teste aqui. O decorator, a tag e o admin são exercitados por requisições
reais.

```
src/feature_flags/
    rollout.py      o bucket derivado, estável e monotônico
    evaluate.py     a ordem das regras, escrita uma vez
    models.py       a tabela de flags
    cache.py        leitura cacheada e os três receivers de invalidação
    api.py          flag_is_active, com memoização por requisição
    decorators.py   flag_required
    templatetags/   a tag e o filtro
    admin.py        o botão, que é o motivo de tudo isso
tests/              62 testes
```

## English summary

Database-backed feature flags for Django: an admin toggle, a **sticky**
percentage rollout, user and group allowlists, a time window, a view decorator
and a template tag. One runtime dependency: Django.

The requirement that shapes the design is stickiness. Somebody who sees a
feature at 10:00 has to still see it at 10:01, and somebody inside at 10% has
to still be inside at 11%, or the rollout becomes a flicker that makes the
feature look broken and the metrics meaningless.

- The bucket is **derived**, not stored: `sha256(flag + ":" + user_pk) % 100`.
  Storing an assignment per user per flag would work, at the cost of a table
  growing with users times flags.
- Python's `hash()` is deliberately not used: it is salted per process, so it
  would answer differently in every worker. It is the one function that cannot
  work here and the first one anybody reaches for.
- The rollout is **monotonic by construction**, so raising the percentage only
  ever adds subjects. A test sweeps 0 to 100 and requires the set to only grow.
- A **missing flag is off**, because the alternative is that a typo in a flag
  name ships a half-built feature to everybody.
- `staff_only` is a **gate**, not a rule: an allowlisted non-staff user is
  still refused. The allowlist sits **above** the percentage, so the team can
  see a feature whatever their bucket.
- An **anonymous** visitor is off below 100%: there is no stable identity to
  bucket, and a coin flip would answer differently on consecutive page loads.
- Cache invalidation covers `m2m_changed` as well as `post_save`, because the
  allowlists live in separate tables and saving the flag never touches them —
  without it, adding somebody to a flag did nothing until the timeout expired.
- The admin's bulk action saves one row at a time rather than using
  `queryset.update()`, which sends no signal and would leave the cache serving
  the old answer.

Code and docstrings are in English; the sections above are in Portuguese.

## Licença

MIT. Veja [LICENSE](LICENSE).
