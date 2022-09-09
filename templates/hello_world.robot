*** Settings ***
Suite Setup     Setup
Suite Teardown  Teardown
Test Teardown   Test Teardown
Resource        ${RENODEKEYWORDS}
Test Timeout	30 s

*** Test Cases ***
{{sample_name}} on {{board_name}}
    [Timeout]	30 s
    ${x}=                       Execute Command         include @${EXECDIR}/artifacts/{{board_name}}-{{sample_name}}/{{board_name}}-{{sample_name}}.resc
    Create Terminal Tester      sysbus.{{uart_name}}    timeout=5
    Start Emulation
    Wait For Line On Uart       Hello World! {{config_board_name}}	timeout=0.1
