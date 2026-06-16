export interface Usuario {
  id: number;
  nome: string;
  email: string | null;
  cpf_mascarado: string | null;
  tipo_perfil: TipoPerfil;
  must_change_password: boolean;
  coroinha_id: number | null;
  responsavel_id: number | null;
}

export type TipoPerfil =
  | "Coordenador"
  | "Secretario"
  | "Padre"
  | "Pai"
  | "Coroinha";

export interface AuthResponse {
  access: string;
  refresh: string;
  usuario: Usuario;
}

export interface Coroinha {
  id: number;
  nome: string;
  data_nascimento: string;
  idade: number;
  turma: string;
  status: string;
  escola: string;
  serie: string;
  foto_url?: string | null;
}

export interface Aniversariante {
  id: number;
  nome: string;
  data_nascimento: string;
  idade: number;
  dia: number;
  foto_url?: string | null;
  turma: string;
}

export interface EscalaItem {
  id: number;
  coroinha_id: number;
  coroinha_nome: string;
  coroinha_foto_url?: string | null;
  ordem: number;
  funcao?: string | null;
  funcao_label?: string | null;
  presenca_status: string | null;
}

export interface Escala {
  id: number;
  data: string;
  missa: number;
  missa_nome: string;
  modo: string;
  criado_em: string;
  itens: EscalaItem[];
}

export interface Missa {
  id: number;
  nome: string;
  dia_semana: string | null;
  dia_mes: number | null;
  horario: string;
  ativa: boolean;
  recorrencia?: string;
}

export interface Inscricao {
  id: number;
  status: string;
  dados: {
    coroinha?: { nome?: string; data_nascimento?: string };
    responsavel?: { cpf?: string; nome_mae?: string };
  };
  criado_em: string;
}

export interface Formacao {
  id: number;
  titulo: string;
  data: string;
  descricao: string;
  concluintes_count: number;
}

export interface FormacaoConclusaoRow {
  coroinha_id: number;
  coroinha_nome: string;
  concluido: boolean;
}

export interface Mensagem {
  id: number;
  canal: string;
  corpo: string;
  destinatarios_nomes: string[];
  enviada_em: string;
  simulacao: boolean;
}

export interface Noticia {
  id: number;
  titulo: string;
  conteudo: string;
  destaque: boolean;
  publicado_em: string;
  ativo: boolean;
  autor_nome?: string;
}

export interface Documento {
  id: number;
  titulo: string;
  descricao: string;
  url: string;
  categoria: string;
  ativo: boolean;
}

export interface ProximaEscala {
  id: number;
  data: string;
  missa: string;
  coroinhas_count: number;
}

export interface CoroinhaResumo extends Coroinha {
  escalas_total: number;
  presencas_total: number;
  faltas_total: number;
  formacoes_concluidas: number;
  formacoes_total?: number;
  proxima_escala: { data: string; missa: string } | null;
  escalas: { data: string; missa: string; presenca: string | null }[];
  formacoes: { titulo: string; data: string; descricao: string }[];
}

export interface DashboardStats {
  total_coroinhas: number;
  ativos: number;
  em_formacao: number;
  inscricoes_pendentes: number;
  escalas_mes: number;
  faltas_mes: number;
  formacoes_realizadas: number;
}

export interface RelatorioGeral {
  total_escalas: number;
  formacoes_realizadas: number;
  taxa_presenca: number;
  por_status: Record<string, number>;
  por_turma: Record<string, number>;
  top_escalados: { nome: string; escalas: number }[];
}

export interface PresencaResumoRow {
  coroinha_id: number;
  nome: string;
  escalas: number;
  presencas: number;
  faltas: number;
  percentual: number | null;
}
