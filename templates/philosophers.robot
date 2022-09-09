*** Settings ***
Suite Setup     Setup
Suite Teardown  Teardown
Test Teardown   Test Teardown
Resource        ${RENODEKEYWORDS}
Test timeout	30 s

*** Test Cases ***
{{sample_name}} on {{board_name}}
    ${x}=                       Execute Command             include @${EXECDIR}/artifacts/{{board_name}}-{{sample_name}}/{{board_name}}-{{sample_name}}.resc
    Create Terminal Tester      sysbus.{{uart_name}}        timeout=5
    Start Emulation
    Wait For Line On Uart       Philosopher 5.*THINKING     treatAsRegex=true	timeout=0.1
    Wait For Line On Uart       Philosopher 5.*HOLDING      treatAsRegex=true
    Wait For Line On Uart       Philosopher 5.*EATING       treatAsRegex=true
