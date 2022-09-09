*** Settings ***
Suite Setup     Setup
Suite Teardown  Teardown
Test Teardown   Test Teardown
Resource        ${RENODEKEYWORDS}
Test timeout	30 s

*** Test Cases ***
{{sample_name}} on {{board_name}}
    ${x}=                       Execute Command         include @${EXECDIR}/artifacts/{{board_name}}-{{sample_name}}/{{board_name}}-{{sample_name}}.resc
    Create Terminal Tester      sysbus.{{uart_name}}    timeout=5
    Write Char Delay            0.01
    Start Emulation
    Wait For Prompt On Uart     uart:~$	timeout=0.1
    Write Line To Uart
    Wait For Prompt On Uart     uart:~$
    Write Line To Uart          demo board
    Wait For Line On Uart       {{config_board_name}}
