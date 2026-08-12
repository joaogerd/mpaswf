# Configurações do MPASWF

A configuração recomendada é dividida em dois arquivos, seguindo a mesma ideia usada no MPAS-BMatrix:

```text
configs/
├── jaci-x1.10242.yaml   # plataforma: caminhos, executáveis, assets e PBS
└── mpas-x1.10242.yaml   # workflow: campanha, GFS/WPS, produtos e templates
```

O usuário **não executa os dois arquivos separadamente**. A interface do MPASWF permanece a mesma. Passe somente a configuração de plataforma:

```bash
CONFIG=configs/jaci-x1.10242.yaml

mpaswf run --phase prepare  --config "$CONFIG"
mpaswf run --phase init     --config "$CONFIG" --submit --wait
mpaswf run --phase forecast --config "$CONFIG" --submit --wait
mpaswf run --phase manifest --config "$CONFIG"
```

A configuração `jaci-x1.10242.yaml` contém:

- diretórios da campanha;
- executáveis WPS e MPAS;
- caminhos dos arquivos fixos da malha;
- backend `local`/`pbs`;
- filas, recursos, módulos e variáveis de ambiente PBS.

Ela aponta para o contrato do workflow por meio de:

```yaml
workflow:
  configuration: mpas-x1.10242.yaml
```

O arquivo `mpas-x1.10242.yaml` contém:

- tempos válidos e leads da campanha;
- convenção dos arquivos GFS;
- contrato de execução do WPS;
- nomes dos produtos MPAS;
- nomes dos templates;
- definição do produto static;
- regras básicas de validação.

O loader faz um **deep merge** dos dois documentos. O contrato do workflow é carregado primeiro; a configuração de plataforma pode sobrescrever apenas os campos necessários. Listas são tratadas como valores completos e não são concatenadas automaticamente.

## Compatibilidade

O formato antigo com um único YAML completo continua suportado. `examples/config.yaml` é mantido como exemplo autocontido e como teste de compatibilidade. Assim, scripts externos e o tutorial do MPAS-BMatrix que chamam:

```bash
mpaswf run --phase ... --config "$MPASWF_CONFIG"
```

não precisam ser alterados.

Consulte também [`docs/configuration.md`](../docs/configuration.md) para a descrição detalhada de cada bloco.
