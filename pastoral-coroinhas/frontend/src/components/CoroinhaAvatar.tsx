"use client";

import Image from "next/image";

interface CoroinhaAvatarProps {
  nome: string;
  fotoUrl?: string | null;
  size?: "sm" | "md" | "lg";
  className?: string;
}

const sizes = {
  sm: "size-8 text-xs",
  md: "size-10 text-sm",
  lg: "size-16 text-2xl",
};

const px = { sm: 32, md: 40, lg: 64 };

export function CoroinhaAvatar({ nome, fotoUrl, size = "md", className = "" }: CoroinhaAvatarProps) {
  const initial = nome?.charAt(0)?.toUpperCase() || "?";
  const dim = px[size];

  if (fotoUrl) {
    return (
      <Image
        src={fotoUrl}
        alt={nome}
        width={dim}
        height={dim}
        className={`rounded-full object-cover shrink-0 ${sizes[size]} ${className}`}
        unoptimized
      />
    );
  }

  return (
    <div
      className={`rounded-full bg-gradient-gold text-burgundy-deep font-display font-bold grid place-items-center shrink-0 shadow-gold ${sizes[size]} ${className}`}
      aria-hidden
    >
      {initial}
    </div>
  );
}
