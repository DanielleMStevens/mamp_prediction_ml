import torch
import torch.nn as nn
from transformers import AutoTokenizer, AutoModel
import math

class FiLMWithAttention(nn.Module):
    def __init__(self, feature_dim):
        super(FiLMWithAttention, self).__init__()
        self.key_proj = nn.Linear(feature_dim, feature_dim)
        self.value_proj = nn.Linear(feature_dim, feature_dim)
        self.query_proj = nn.Linear(feature_dim, feature_dim)
        self.out_proj = nn.Linear(feature_dim, feature_dim * 2)  # gamma and beta

    def forward(self, x, z, x_mask, z_mask):
        # x: (batch_size, seq_len_x, feature_dim)
        # z: (batch_size, seq_len_z, feature_dim)
        query = self.query_proj(x)  # Shape: (batch_size, seq_len_x, feature_dim)
        keys = self.key_proj(z)  # Shape: (batch_size, seq_len_z, feature_dim)
        values = self.value_proj(z)  # Shape: (batch_size, seq_len_z, feature_dim)

        # Compute attention mask
        attention_mask = x_mask.unsqueeze(2) & z_mask.unsqueeze(1)  # Shape: (batch_size, seq_len_x, seq_len_z)
        attention_mask = attention_mask.float().masked_fill(~attention_mask, float('-inf'))
        feature_dim = x.shape[-1]
        # Compute attention
        attention_weights = torch.softmax(
            torch.matmul(query, keys.transpose(-2, -1)) / (feature_dim ** 0.5) + attention_mask, dim=-1
        )
        context = torch.matmul(attention_weights, values)  # Shape: (batch_size, seq_len_x, feature_dim)

        # Generate gamma and beta
        gamma_beta = self.out_proj(context)  # Shape: (batch_size, seq_len_x, feature_dim * 2)
        gamma, beta = torch.chunk(gamma_beta, 2, dim=-1)
        return gamma * x + beta  # Apply FiLM

# class Attention(Module):
#     def __init__(
#         self,
#         dim,
#         dim_head = 64,
#         heads = 8,
#         dim_context = None,
#         norm_context = False,
#         num_null_kv = 0,
#         flash = False
#     ):
#         super().__init__()
#         self.heads = heads
#         self.scale = dim_head ** -0.5
#         inner_dim = dim_head * heads

#         dim_context = default(dim_context, dim)

#         self.norm = nn.LayerNorm(dim)
#         self.context_norm = nn.LayerNorm(dim_context) if norm_context else nn.Identity()

#         self.attend = Attend(flash = flash)        

#         self.num_null_kv = num_null_kv
#         self.null_kv = nn.Parameter(torch.randn(2, num_null_kv, dim_head))

#         self.to_q = nn.Linear(dim, inner_dim, bias = False)
#         self.to_kv = nn.Linear(dim_context, dim_head * 2, bias = False)
#         self.to_out = nn.Linear(inner_dim, dim, bias = False)

#     def forward(
#         self,
#         x,
#         context = None,
#         mask = None
#     ):
#         b = x.shape[0]

#         if exists(context):
#             context = self.context_norm(context)

#         kv_input = default(context, x)

#         x = self.norm(x)

#         q, k, v = self.to_q(x), *self.to_kv(kv_input).chunk(2, dim = -1)

#         if self.num_null_kv > 0:
#             null_k, null_v = repeat(self.null_kv, 'kv n d -> kv b n d', b = b).unbind(dim = 0)
#             k = torch.cat((null_k, k), dim = -2)
#             v = torch.cat((null_v, v), dim = -2)

#         if exists(mask):
#             mask = F.pad(mask, (self.num_null_kv, 0), value = True)
#             mask = rearrange(mask, 'b j -> b 1 1 j')

#         q = rearrange(q, 'b n (h d) -> b h n d', h = self.heads)

#         out = self.attend(q, k, v, mask = mask)

#         out = rearrange(out, 'b h n d -> b n (h d)')
#         return self.to_out(out)

# class CrossAttention(nn.Module):
#     def __init__(
#         self,
#         dim,
#         hidden_dim,
#         heads = 8,
#         dim_head = 64,
#         flash = False
#     ):
#         super().__init__()
#         self.attn = Attention(
#             dim = hidden_dim,
#             dim_context = dim,
#             norm_context = True,
#             num_null_kv = 1,
#             dim_head = dim_head,
#             heads = heads,
#             flash = flash
#         )

#     def forward(
#         self,
#         condition,
#         hiddens,
#         mask = None
#     ):
#         return self.attn(hiddens, condition, mask = mask) + hiddens

class FiLM(nn.Module):
    def __init__(self, feature_dim):
        super(FiLM, self).__init__()
        self.fc = nn.Linear(feature_dim, feature_dim * 2)  # Generate gamma and beta

    def forward(self, x, z):
        # x: (batch_size, feature_dim)
        # z: (batch_size, feature_dim)
        gamma_beta = self.fc(z)  # Shape: (batch_size, feature_dim * 2)
        gamma, beta = torch.chunk(gamma_beta, 2, dim=-1)  # Split into gamma and beta
        return gamma * x + beta  # Apply FiLM

class AMPWithReceptorModel(nn.Module):
    def __init__(self, args=None):
        super().__init__()
        self.model = AutoModel.from_pretrained("chandar-lab/AMPLIFY_350M", trust_remote_code=True)

        for param in self.model.parameters():
            param.requires_grad = False     

        E = self.model.config.hidden_size

        self.net = nn.Sequential(
            nn.Linear(E, E),
            nn.ReLU(),
            nn.Linear(E, int(E // 2)),
            nn.ReLU(),
            nn.Linear(int(E // 2), 3),
        )

        self.film = FiLM(E)
        self.tokenizer = AutoTokenizer.from_pretrained("chandar-lab/AMPLIFY_350M", trust_remote_code=True)

    def forward(self, batch_x):
        batch_peptide_x = batch_x['peptide_x']
        batch_receptor_x = batch_x['receptor_x']
        peptide_embeddings = self.model(batch_peptide_x.input_ids, attention_mask=batch_peptide_x.attention_mask.float(), output_hidden_states=True).hidden_states[-1][:, 0, :]
        receptor_embeddings = self.model(batch_receptor_x.input_ids, attention_mask=batch_receptor_x.attention_mask.float(), output_hidden_states=True).hidden_states[-1][:, 0, :]
        embeddings = self.film(peptide_embeddings, receptor_embeddings)
        return self.net(embeddings)
    
    def get_tokenizer(self):
        return self.tokenizer

    def get_new_padded(self, inputs):
        max_seq_len = max([len(seq) for seq in inputs["input_ids"]])
        pad_to_multiple_of_8 = math.ceil(max_seq_len / 8) * 8

        # Step 4: Tokenize and pad sequences to the new length
        padded_input_ids = []
        padded_attn_masks = []
        for seq, attn_mask in zip(inputs["input_ids"], inputs["attention_mask"]):
            # Calculate padding size to make the sequence length a multiple of 8
            padding_size = pad_to_multiple_of_8 - len(seq)
            
            # Pad the sequence with padding token
            padded_seq = torch.cat([seq, torch.full((padding_size,), self.tokenizer.pad_token_id)])
            padded_input_ids.append(padded_seq)
            padded_attn_masks.append(torch.cat([attn_mask, torch.full((padding_size,), 0)]))

        batch_input_ids = torch.stack(padded_input_ids)
        batch_attn_mask = torch.stack(padded_attn_masks).float()

        return batch_input_ids, batch_attn_mask

    def collate_fn(self, batch):
        inputs = {}
        
        x_dict = {}

        peptide_x = self.tokenizer([example['peptide_x'] for example in batch],
                return_tensors='pt', padding=True)
        
        peptide_x_input_ids, peptide_x_attn_mask = self.get_new_padded(peptide_x)

        peptide_x['input_ids'] = peptide_x_input_ids
        peptide_x['attention_mask'] = peptide_x_attn_mask
        
        receptor_x = self.tokenizer([example['receptor_x'] for example in batch],
                return_tensors='pt', padding=True)
        
        receptor_x_input_ids, receptor_x_attn_mask = self.get_new_padded(receptor_x)

        receptor_x['input_ids'] = receptor_x_input_ids
        receptor_x['attention_mask'] = receptor_x_attn_mask

        x_dict['peptide_x'] = peptide_x
        x_dict['receptor_x'] = receptor_x
        
        inputs['y'] = torch.tensor([example['y'] for example in batch])

        inputs['x'] = x_dict
 
        return inputs

    def batch_decode(self, batch):
        peptide_decoded_ls = self.tokenizer.batch_decode(batch['x']['peptide_x'].input_ids, skip_special_tokens=True)
        receptor_decoded_ls = self.tokenizer.batch_decode(batch['x']['receptor_x'].input_ids, skip_special_tokens=True)
        
        return [f"{peptide}:{receptor}" for peptide, receptor in zip(peptide_decoded_ls, receptor_decoded_ls)]