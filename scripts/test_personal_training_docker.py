"""Integration acceptance with an isolated disposable PostgreSQL DATABASE.

Requires the local Compose postgres and built paper-trading image. Synthetic
fixtures are labelled SYNTHETIC_TEST_ONLY and NEVER enter the business database.
No host ports are published. Only the database/container created by this process
are removed. PostgreSQL credentials are kept in memory and are never printed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
import uuid
from datetime import date, datetime, time as daytime, timedelta, timezone


def command(args, *, data=None, env=None, check=True):
    result = subprocess.run(args, input=data, text=True, encoding='utf-8', capture_output=True, env=env, timeout=90)
    if check and result.returncode:
        raise RuntimeError(f"Command failed: {args[0:3]} (exit {result.returncode})")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--postgres-container', default='ai-quant-postgres-1')
    parser.add_argument('--network', default='ai-quant_data')
    parser.add_argument('--image', default='ai-quant-paper-trading-service:latest')
    args = parser.parse_args()
    suffix = uuid.uuid4().hex[:12]
    database = 'test_personal_' + suffix
    container = 'ai-quant-personal-test-' + suffix
    assert re.fullmatch(r'test_personal_[0-9a-f]{12}', database)
    created_database = created_container = False
    report = []

    def sql(body, db=database):
        return command(['docker', 'exec', '-i', args.postgres_container, 'sh', '-c',
                        'exec psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1"',
                        'test-psql', db], data=body).stdout

    def http(path, payload=None, expected=200):
        cmd = ['docker', 'exec', '-i', container, 'curl', '--silent', '--show-error', '--max-time', '30',
               '--write-out', '\n%{http_code}', '-H', 'Content-Type: application/json']
        if payload is not None:
            cmd += ['--data-binary', '@-']
        cmd += ['http://127.0.0.1:8083' + path]
        result = command(cmd, data=json.dumps(payload) if payload is not None else None, check=False)
        content, _, status = result.stdout.rpartition('\n')
        if status != str(expected):
            raise RuntimeError(f"{path}: expected {expected}, received {status}: {content[:500]}")
        return json.loads(content) if content else None

    try:
        env_rows = json.loads(command(['docker', 'inspect', '--format', '{{json .Config.Env}}', args.postgres_container]).stdout)
        pg = dict(row.split('=', 1) for row in env_rows if '=' in row)
        env = dict(os.environ, DATABASE_USERNAME=pg['POSTGRES_USER'], DATABASE_PASSWORD=pg['POSTGRES_PASSWORD'])
        sql(f'create database {database};', db='postgres')
        created_database = True
        command(['docker', 'run', '--rm', '-d', '--name', container, '--network', args.network,
                 '--read-only', '--tmpfs', '/tmp:rw,noexec,nosuid,size=128m', '--memory', '512m', '--cpus', '1',
                 '--security-opt', 'no-new-privileges:true',
                 '-e', f'DATABASE_URL=jdbc:postgresql://postgres:5432/{database}',
                 '-e', 'DATABASE_USERNAME', '-e', 'DATABASE_PASSWORD', '-e', 'NACOS_ENABLED=false',
                 '-e', 'DATABASE_POOL_SIZE=4', '-e', 'DATABASE_MIN_IDLE=1', '-e', 'SPRING_FLYWAY_SCHEMAS=paper_trading',
                 '-e', 'JAVA_TOOL_OPTIONS=-Djava.io.tmpdir=/tmp -Duser.home=/tmp', args.image], env=env)
        created_container = True
        for attempt in range(45):
            try:
                http('/actuator/health/readiness')
                break
            except RuntimeError:
                if attempt == 44:
                    raise
                time.sleep(1)
        version = http('/api/v1/paper/personal/versions')[0]
        bars = []
        day = date(2025, 1, 2)
        for i in range(134):
            while day.weekday() >= 5:
                day += timedelta(days=1)
            close = 80 + i * .3 if i < 100 else 110
            open_, high, low = close - .1, close + .5, close - .5
            if i == 130:
                open_, high, low, close = 110, 114, 110, 113
            if i == 131:
                open_, high, low, close = 110.8, 112.5, 110.3, 111.5
            stamp = datetime.combine(day, daytime(), timezone.utc).isoformat()
            bars.append((stamp, open_, high, low, close, 2000 if i == 130 else 1000))
            day += timedelta(days=1)

        def fixture(label, next_prices, *, held=False, roll=False, manual=False):
            sid = str(uuid.uuid4())
            opened_order = str(uuid.uuid4())
            seed_command = str(uuid.uuid4())
            statements = [f"""
                insert into paper_trading.paper_session
                (id,name,mode,symbol,status,data_source,data_timestamp,initial_cash,cash_balance,equity,
                 margin_rate,fee_rate,slippage_ticks,max_participation_rate,auto_roll,current_bar_index,total_bars,
                 current_market_time,current_contract,current_price,volume_multiple,price_tick,margin_per_lot,commission_per_lot)
                values('{sid}','SYNTHETIC_TEST_ONLY:{label}','HISTORICAL','CJ0','ACTIVE','SYNTHETIC_TEST_ONLY','{bars[0][0]}',
                 100000,{99998 if held else 100000},{100008 if held else 100000},.15,.0001,1,.05,false,131,134,'{bars[131][0]}','CJ505',111.5,10,.1,2000,1);
                insert into paper_trading.paper_position(session_id,contract,direction,lots,average_price,margin_occupied,unrealized_pnl)
                values('{sid}','CJ505',{1 if held else 0},{2 if held else 0},{111 if held else 0},{4000 if held else 0},{10 if held else 0});
                insert into paper_trading.paper_contract_spec values('{sid}','CJ505',10,.1,2000,1);
                insert into paper_trading.personal_training(session_id,version_id,training_mode,training_start,rules,stop_price,risk_budget,peak_equity,entry_bar)
                values('{sid}','{version['id']}','{'GUIDED' if manual else 'RULE_REPLAY'}','{bars[131][0][:10]}',
                    '{json.dumps(version['rules'])}'::jsonb,{110 if held else 'null'},{100 if held else 0},{100038 if held else 100000},{130 if held else 'null'});
                """]
            for i, raw in enumerate(bars):
                stamp, o, h, low, close, volume = raw
                if i == 132:
                    o, h, low, close = next_prices
                contract = 'CJ509' if roll and i >= 132 else 'CJ505'
                statements.append(f"insert into paper_trading.paper_scenario_bar(session_id,bar_index,market_time,contract,open_price,high_price,low_price,close_price,volume,open_interest) values('{sid}',{i},'{stamp}','{contract}',{o},{h},{low},{close},{volume},10000);")
            if held:
                statements.append(f"""
                    insert into paper_trading.paper_order(id,session_id,client_order_id,side,offset_type,order_type,quantity,remaining_quantity,status,eligible_bar_index)
                    values('{opened_order}','{sid}','personal-entry-{seed_command}','BUY','OPEN','MARKET',2,0,'FILLED',130);
                    insert into paper_trading.paper_fill(id,session_id,order_id,event_type,contract,side,offset_type,quantity,market_price,fill_price,fee,slippage_cost,realized_pnl,reason,market_time)
                    values('{uuid.uuid4()}','{sid}','{opened_order}','ORDER','CJ505','BUY','OPEN',2,111,111,2,0,0,'SYNTHETIC_TEST_ONLY seed position','{bars[130][0]}');
                    insert into paper_trading.personal_training_event(id,session_id,command_id,bar_index,market_time,action,compliant,emotion,notes,plan,outcome)
                    values('{uuid.uuid4()}','{sid}','{seed_command}',130,'{bars[130][0]}','FOLLOW',true,0,'SYNTHETIC_TEST_ONLY seed',
                    '{{"riskBudget":100}}','{{"afterEquity":100038}}');
                    """)
            if roll:
                statements.append(f"""
                    insert into paper_trading.paper_contract_spec values('{sid}','CJ509',20,.2,4000,2);
                    insert into paper_trading.paper_roll_event(session_id,execution_date,from_contract,to_contract,old_open,new_open)
                    values('{sid}','{bars[132][0][:10]}','CJ505','CJ509',112,152);
                    """)
            sql('\n'.join(statements))
            return sid

        def step(sid, **override):
            payload = dict(commandId=str(uuid.uuid4()), expectedBarIndex=131, action='FOLLOW', emotion=0,
                           riskAccepted=True, stopAccepted=True, noRevenge=True, notes='SYNTHETIC_TEST_ONLY')
            payload.update(override)
            return http(f'/api/v1/paper/personal/runs/{sid}/step', payload), payload

        sid = fixture('same-bar-protection', (111.7, 112, 109, 111))
        result, payload = step(sid)
        assert result['session']['position']['lots'] == 0
        assert result['session']['fillCount'] == 2
        exits = [f for f in result['session']['fills'] if f['offset'] == 'CLOSE']
        assert exits[0]['fillPrice'] == 109.9, exits
        assert result['metrics']['closedTradeCount'] == 1
        repeated = http(f'/api/v1/paper/personal/runs/{sid}/step', payload)
        assert repeated['session']['currentBarIndex'] == 132 and repeated['session']['fillCount'] == 2
        report.append('same-bar protection and idempotency: PASS')

        sid = fixture('gap-invalidates-entry', (109, 112, 108, 111))
        result, _ = step(sid)
        assert result['session']['fillCount'] == 0
        assert result['session']['orders'][0]['status'] == 'REJECTED'
        report.append('open beyond structural stop rejects entry: PASS')

        sid = fixture('limit-not-touched', (115, 116, 114, 115))
        result, _ = step(sid)
        assert result['session']['fillCount'] == 0
        assert result['session']['orders'][0]['status'] == 'CANCELLED'
        report.append('unfilled one-day limit expires: PASS')

        sid = fixture('held-gap-stop', (100, 103, 99, 101), held=True)
        result, _ = step(sid)
        assert result['session']['position']['lots'] == 0
        assert result['session']['equity'] == 99774.0, result['session']['equity']
        assert result['metrics']['lossBeyondBudgetCount'] == 1
        report.append('held gap fills adversely and can exceed budget: PASS')

        sid = fixture('observed-roll-old-leg', (152, 154, 151, 153), held=True, roll=True)
        result, _ = step(sid)
        assert result['session']['position']['lots'] == 0
        assert result['session']['currentContract'] == 'CJ509'
        assert result['session']['equity'] == 100014.0, result['session']['equity']
        assert result['session']['volumeMultiple'] == 20
        assert result['session']['fillCount'] == 2
        report.append('roll closes old leg with old spec; gap is not profit: PASS')

        sid = fixture('manual-checklist', (111.7, 112, 111, 111.8), manual=True)
        result, _ = step(sid, riskAccepted=False)
        assert result['session']['fillCount'] == 0
        events = http(f'/api/v1/paper/personal/runs/{sid}/events')
        assert events['items'][0]['compliant'] is False
        http(f'/api/v1/paper/sessions/{sid}/advance', {'steps': 1}, expected=409)
        report.append('manual checklist and generic-endpoint bypass blocked: PASS')
        print(json.dumps({'fixtureOrigin': 'SYNTHETIC_TEST_ONLY', 'isolatedDatabase': database,
                          'checks': report}, ensure_ascii=True))
    finally:
        if created_container:
            command(['docker', 'stop', '--time', '5', container], check=False)
        if created_database:
            # The identifier is a locally generated, verified name created above.
            assert re.fullmatch(r'test_personal_[0-9a-f]{12}', database)
            sql(f'drop database {database} with (force);', db='postgres')
            print('Temporary test database and container cleaned up; business data unchanged.')


if __name__ == '__main__':
    main()
