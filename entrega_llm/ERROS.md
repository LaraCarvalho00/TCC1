# Erros

Nenhuma etapa falhou depois que o patch foi aplicado. Os 49 testes, o teste curto do banco, o banco de 50 questões, as 480 execuções e as 1440 execuções da varredura terminaram com código de saída 0.

Antes disso, a etapa 1 parou porque o arquivo ainda não estava na raiz:

```
$ git apply --check calibracao_sem_lider_e_banco_llm.patch
error: can't open patch 'calibracao_sem_lider_e_banco_llm.patch': No such file or directory
```

Código de saída: 128. O patch foi gravado em seguida e a etapa 1 recomeçou.

Na varredura, o processo em sandbox escreveu `Failed to create PreventUserIdleSystemSleep assertion`. As 1440 execuções foram concluídas. O banco, fora do sandbox, já segurava o `caffeinate` nessa janela.
