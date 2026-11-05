# Fluxo obrigatório de desenvolvimento — Git Flow simplificado

Esta política se aplica a mudanças de código, configuração, infraestrutura,
templates, contratos científicos e documentação operacional.

## Branches

- **main:** estado estável, publicado somente por PR de `develop`. Nunca
  desenvolver diretamente em `main`.
- **develop:** integração contínua de funcionalidades previamente testadas.
  Os testes precisam passar após cada merge.
- **feature/<assunto>:** implementação isolada, sempre derivada do estado
  atual de `develop`; PR de retorno para `develop`.

Fluxo recomendado:

```text
main → develop → feature/<assunto>
                    ↓ PR + testes + revisão
                 develop
                    ↓ suíte integrada + aceite científico
                   main
                    ↓ tag SemVer
                 vMAJOR.MINOR.PATCH
```

## Critérios para integrar uma feature em develop

1. Investigar o código e comportamento anterior, incluindo compatibilidade.
2. Implementar a funcionalidade somente em `feature/*`, com commits coerentes.
3. Atualizar testes automatizados, incluindo casos inválidos e outras malhas,
   resoluções e níveis quando aplicável.
4. Verificar a CI do PR, com todas as versões de Python suportadas.
5. Documentar mudanças de configuração, interfaces e limitações científicas.
6. Revisar o diff e integrar o PR em `develop`, preservando histórico e
   atribuição de autoria.
7. Confirmar novamente a CI de `develop`.

## Critérios para promover develop a main

A promoção somente ocorre via PR `develop → main`, sem bypass de CI ou
proteção de branches. Requer:

- Suíte automatizada **integrada** aprovada em `develop`, sem regressões;
- Contrato compatível entre MPASWF e MPAS-BMatrix e testado nas duas pontas;
- Configuração e testcase histórico reproduzíveis, preservados fora do código;
- Documentação de instalação, migração e erros revisada;
- Para alterações com efeito potencial sobre previsão, amostragem NMC ou
  calibração B: **execução científica no JACI**, usando dados e versão de
  executáveis identificados, mais comparação numérica dos produtos com
  referências e tolerâncias acordadas;
- Nenhuma pendência de severidade crítica que comprometa a corretude.

Passar no pytest **não** prova equivalência numérica do MPAS/JEDI/SABER
com dados reais. Se não houver acesso a dados, binários ou HPC para validar
cientificamente, mantenha as features aprovadas em `develop` e documente
por que a promoção ainda está bloqueada.

## Segurança e governança

- Não usar force push, reset --hard ou sobrescrita de trabalho de terceiros.
- Tratar mudanças de API/manifesto como contratos versionados, preservando o
  consumidor anterior quando possível.
- O workflow `.github/workflows/gitflow-policy.yml` verifica se PRs para
  `main` vêm de `develop` e PRs para `develop` vêm de `feature/*`.
- A CI também roda em pushes para `develop`. O administrador do GitHub
  deve tornar obrigatórios os checks da CI e da política de branches, além
  de restringir pushes diretos a `main` e `develop`. Workflow de CI sem
  proteção de branch **não bloqueia** um push direto por quem tem permissão.
- Criar tag SemVer somente após merge validado em `main` e verificação
  do commit publicado. A tag deve apontar para o commit de produção.
