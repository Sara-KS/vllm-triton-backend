import torch

# TODO: will be necessary for AMD
# if torch.version.hip:
#     from flash_attn import flash_attn_varlen_func, flash_attn_func
# else:
from vllm.vllm_flash_attn import flash_attn_with_kvcache, flash_attn_varlen_func
from .base import DecodeCaller, PrefillCaller


class FlashAttnDecodeCaller(DecodeCaller):
    @staticmethod
    def make_call_func(
        output,
        query,
        key_cache,
        value_cache,
        num_seqs,  # unused
        seq_lens,
        max_seq_len,  # unused
        scale,
        block_tables,
        alibi_slopes,
        kv_cache_dtype,  # unused
    ):
        def transform_kv_cache(x):
            out = torch.transpose(x, 1, 3)
            out = torch.transpose(out, 2, 3)
            return out.contiguous()

        key_cache_flash_attn = transform_kv_cache(key_cache)
        value_cache_flash_attn = transform_kv_cache(value_cache)

        q = query.unsqueeze(1)

        call_func_under_test = lambda: flash_attn_with_kvcache(
            q=q,
            k_cache=key_cache_flash_attn,
            v_cache=value_cache_flash_attn,
            out=None,
            softmax_scale=scale,
            causal=True,
            cache_seqlens=seq_lens,
            window_size=(-1, 1),
            block_table=block_tables,
            softcap=0,
            alibi_slopes=alibi_slopes,
        )

        return call_func_under_test

    @classmethod
    def select_output(cls, x, y):
        return y.squeeze(1)

    @staticmethod
    def requires_allocated_output() -> bool:
        return False


class FlashAttnPrefillCaller(PrefillCaller):
    @staticmethod
    def make_call_func(
        output,  # unused
        query,
        key_cache,
        value_cache,
        cu_seqlens_q,
        cu_seqlens_k,
        max_seqlen_q,
        max_seqlen_k,
        softmax_scale,
        causal,
        # kv_cache_dtype,  # unused
    ):
        # q: (total_q, nheads, headdim), where total_q = total number of query tokens in the batch.
        # k: (total_k, nheads_k, headdim), where total_k = total number of key tokens in the batch.
        # v: (total_k, nheads_k, headdim), where total_k = total number of key tokens in the batch.
        # cu_seqlens_q: (batch_size + 1,), dtype torch.int32. The cumulative sequence lengths
        #    of the sequences in the batch, used to index into q.
        # cu_seqlens_k: (batch_size + 1,), dtype torch.int32. The cumulative sequence lengths
        #    of the sequences in the batch, used to index into kv.
        # max_seqlen_q: int. Maximum query sequence length in the batch.
        # max_seqlen_k: int. Maximum key sequence length in the batch.
        # out: (total, nheads, headdim).

        def call_and_process_output():
            return flash_attn_varlen_func(
                q=query,
                k=key_cache,
                v=value_cache,
                cu_seqlens_q=cu_seqlens_q,
                cu_seqlens_k=cu_seqlens_k,
                max_seqlen_q=max_seqlen_q,
                max_seqlen_k=max_seqlen_k,
                softmax_scale=softmax_scale,
                causal=causal,
            )

        return call_and_process_output

    @staticmethod
    def requires_allocated_output() -> bool:
        return False
