# Configuração do MPASWF

## Visão geral

O MPASWF aceita duas formas equivalentes de configuração:

1. **formato dividido**, recomendado para uso normal;
2. **formato autocontido**, mantido por compatibilidade.

A interface da linha de comando não muda em nenhum dos casos:

```bash
mpaswf run --phase prepare --config <arquivo.yaml>
```

No formato dividido, `<arquivo.yaml>` é a configuração de plataforma. Ela referencia um segundo YAML com o contrato do workflow. O carregamento e o merge são transparentes para as fases `prepare`, `init`, `forecast` e `manifest`.

## Estrutura recomendada

```text
configs/
├── jaci-x1.10242.yaml
└── mpas-x1.10242.yaml
```

### `jaci-x1.10242.yaml`: plataforma

Contém somente o que depende da máquina ou da instalação:

- `paths`: diretórios de trabalho, GFS, static e templates;
- `executables`: WPS e executáveis MPAS;
- `static.links`: malha, partição e assets fixos;
- `execution`: backend local ou PBS;
- `pbs`: filas, recursos, walltimes, launcher MPI, módulos e ambiente.

O arquivo contém:

```yaml
workflow:
  configuration: mpas-x1.10242.yaml
```

O caminho é resolvido relativamente ao diretório do arquivo de plataforma. Caminhos absolutos também são aceitos.

### `mpas-x1.10242.yaml`: contrato do workflow

Contém o que define a campanha e a forma dos produtos:

- `campaign`;
- `gfs`;
- `wps`;
- `products`;
- `templates`;
- `static.reference_time` e `static.product_template`;
- `validation`.

A separação é intencional: mudar de máquina não deve exigir editar a definição científica/operacional da campanha, e mudar a campanha não deve exigir duplicar caminhos PBS e executáveis.

## Como o merge funciona

O MPASWF carrega primeiro o contrato indicado em `workflow.configuration` e depois faz um merge recursivo da configuração de plataforma sobre ele.

Exemplo:

```yaml
# mpas-x1.10242.yaml
static:
  reference_time: "2010-10-23T00:00:00Z"
  product_template: "x1.10242.static.nc"
```

```yaml
# jaci-x1.10242.yaml
static:
  links:
    - source: /path/x1.10242.grid.nc
      target: x1.10242.grid.nc
```

O resultado visto pelo workflow é:

```yaml
static:
  reference_time: "2010-10-23T00:00:00Z"
  product_template: "x1.10242.static.nc"
  links:
    - source: /path/x1.10242.grid.nc
      target: x1.10242.grid.nc
```

Mapas são combinados recursivamente. Listas não são concatenadas: uma lista definida no arquivo de plataforma substitui integralmente a lista correspondente do contrato. Isso evita combinações implícitas de listas operacionalmente importantes.

## Variáveis de ambiente

Strings YAML passam por expansão de variáveis de ambiente. Assim, é possível escrever:

```yaml
paths:
  work_dir: /p/projetos/monan_das/${USER}/work/mpaswf
```

A expansão ocorre antes da validação e antes da resolução dos caminhos.

## Campanha e pares f024/f048

O bloco `campaign` trabalha com **tempos válidos**:

```yaml
campaign:
  start_valid_time: "2026-06-22T00:00:00Z"
  end_valid_time: "2026-06-25T00:00:00Z"
  interval_hours: 24
  leads_hours: [24, 48]
```

Para cada tempo válido `T`, o MPASWF determina automaticamente os horários de inicialização necessários:

```text
f048: init = T - 48 h, valid = T
f024: init = T - 24 h, valid = T
```

Esse é o contrato usado pelo tutorial do MPAS-BMatrix para gerar pares NMC de mesmo tempo válido.

## Blocos de configuração

### `paths`

```yaml
paths:
  work_dir: ...
  static_dir: ...
  gfs_dir: ...
  cdct_templates_dir: ...
```

`work_dir` é a raiz da campanha. `static_dir` guarda o produto estático reutilizável. `gfs_dir` contém os GRIB2 por ciclo. `cdct_templates_dir` contém os templates WPS/MPAS declarados em `templates`.

### `executables`

```yaml
executables:
  wps_dir: ...
  mpas_init: .../mpas_init_atmosphere
  mpas_atmosphere: .../mpas_atmosphere
```

Os dois executáveis MPAS devem pertencer à mesma instalação/build usada para a campanha.

### `gfs`

Define a convenção de nome dos GRIB2, eventual URL de aquisição e tamanho mínimo aceito. Com `url_template: null`, o MPASWF exige que os arquivos já existam localmente.

### `wps`

Define o nome esperado do `FILE:*`, a Vtable e os comandos `link_grib`/`ungrib`. Os caminhos específicos da instalação WPS vêm de `executables.wps_dir`.

### `products`

Define os nomes físicos dos estados iniciais, restarts e `da_state`. Esses nomes devem permanecer coerentes com os streams usados pelo MPAS.

### `templates`

Define os nomes dos arquivos de template localizados em `paths.cdct_templates_dir`. O MPASWF renderiza cópias nos diretórios de execução; não modifica os templates de origem.

### `static`

O contrato define o nome e o tempo de referência do produto estático. A plataforma define `static.links` porque os caminhos dos assets dependem da máquina.

`x1.10242.static.nc` não deve aparecer em `static.links`: ele é saída do estágio static.

### `execution`

```yaml
execution:
  backend: pbs
```

Valores aceitos: `local` e `pbs`.

### `pbs`

Define recursos dos jobs MPAS, filas, walltimes, launcher MPI, comandos do scheduler, intervalo de polling e ambiente do job.

O smoke PBS real usa a mesma configuração de scheduler e ambiente, mas força uma requisição mínima de 1 CPU / 1 rank MPI.

### `validation`

Define validações mínimas antes de considerar um produto reutilizável. `require_netcdf: true` adiciona validação de abertura NetCDF quando a dependência opcional correspondente está disponível.

## Execução recomendada na JACI

Depois de revisar `configs/jaci-x1.10242.yaml`:

```bash
CONFIG=configs/jaci-x1.10242.yaml

mpaswf pbs-smoke --config "$CONFIG"
mpaswf run --phase prepare --config "$CONFIG"
mpaswf run --phase init --config "$CONFIG" --submit --wait
mpaswf run --phase forecast --config "$CONFIG" --submit --wait
mpaswf run --phase manifest --config "$CONFIG"
```

O manifesto final continua em:

```text
<work_dir>/products/mpas-forecast-manifest.tsv
```

Nenhuma dessas chamadas muda em relação ao contrato já documentado no MPAS-BMatrix.

## Compatibilidade com o formato antigo

Um YAML único contendo todos os blocos continua válido. `examples/config.yaml` é mantido para demonstrar e testar esse formato.

Portanto, qualquer script externo que já faça:

```bash
mpaswf run --phase forecast --config "$MPASWF_CONFIG" --submit --wait
```

continua funcionando sem alteração, independentemente de `$MPASWF_CONFIG` apontar para um YAML autocontido ou para uma configuração de plataforma que referencia o contrato do workflow.
