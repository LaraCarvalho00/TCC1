"""A simulação reutiliza hash sem enfraquecer a verificação pública."""
from dataclasses import replace
import unittest

from sistema.core.ledger import RoundRecord, canonical_hash
from sistema.core.protocol import NetworkState, ProtocolConfig, verify_record, _verify_record_in_group


class VerificacaoOtimizadaTest(unittest.TestCase):
    def test_chamada_publica_recalcula_hash_apos_mutacao(self):
        state = NetworkState(['node-0'], ProtocolConfig())
        record = RoundRecord(kind='round', round_index=0, responses=(('node-0', 1),), state_after={'x': 1}).sealed()
        self.assertTrue(verify_record(state, record, node_id='node-0', own_answer=1, prev_hash='0' * 64, objective='').ok)
        record.state_after['x'] = 2
        self.assertEqual(verify_record(state, record, node_id='node-0', own_answer=1, prev_hash='0' * 64, objective='').reason, 'hash')

    def test_verificacao_precalculada_preserva_voto_e_precedencia(self):
        state = NetworkState(['node-0', 'node-1'], ProtocolConfig())
        valid = RoundRecord(kind='round', round_index=0, responses=(('node-0', 1), ('node-1', 2))).sealed()
        cases = [
            (valid, '0' * 64, 'node-0', 1, ''),
            (valid, 'wrong', 'node-0', 1, 'chain'),
            (replace(valid, hash='wrong'), '0' * 64, 'node-0', 1, 'hash'),
            (replace(valid, responses=(('node-0', 7), ('node-1', 2))), '0' * 64, 'node-0', 1, 'hash'),
            (valid, '0' * 64, 'node-0', 7, 'censored'),
            (valid, '0' * 64, 'node-3', 7, 'censored'),
            (valid, '0' * 64, 'node-0', None, ''),
        ]
        for record, prev, node, answer, reason in cases:
            with self.subTest(expected=reason, prev=prev, node=node, answer=answer):
                original = verify_record(state, record, node_id=node, own_answer=answer, prev_hash=prev, objective='')
                cached = _verify_record_in_group(state, record, node_id=node, own_answer=answer, prev_hash=prev,
                                                 objective='', hash_valid=record.hash == canonical_hash(record.content()),
                                                 responses=record.responses_map())
                self.assertEqual(original, cached)
                self.assertEqual(original.reason, reason)


if __name__ == '__main__':
    unittest.main()
