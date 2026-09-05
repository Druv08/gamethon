// Protect the King - 2D. Shared health implementation.

#include "Components/PTKHealthComponent.h"

#include "GameFramework/Actor.h"
#include "ProtectTheKing2D.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(PTKHealthComponent)

UPTKHealthComponent::UPTKHealthComponent()
{
	// Health is event-driven. Nothing needs to happen every frame, and a
	// component that ticks for no reason costs the same as one that does.
	PrimaryComponentTick.bCanEverTick = false;
}

void UPTKHealthComponent::BeginPlay()
{
	Super::BeginPlay();

	CurrentHealth = MaxHealth;
	bDead = false;

	if (AActor* Owner = GetOwner())
	{
		// Subscribing here rather than requiring callers to use ApplyDamage
		// means UGameplayStatics::ApplyDamage, radial damage and anything else
		// the engine offers all land in the same place.
		Owner->OnTakeAnyDamage.AddDynamic(this, &UPTKHealthComponent::HandleAnyDamage);
	}
}

float UPTKHealthComponent::GetHealthFraction() const
{
	return (MaxHealth > KINDA_SMALL_NUMBER)
		? FMath::Clamp(CurrentHealth / MaxHealth, 0.0f, 1.0f)
		: 0.0f;
}

void UPTKHealthComponent::HandleAnyDamage(AActor* /*DamagedActor*/, float Damage,
	const UDamageType* /*DamageType*/, AController* InstigatedBy, AActor* DamageCauser)
{
	AActor* Source = DamageCauser;
	if (!Source && InstigatedBy)
	{
		Source = InstigatedBy->GetPawn();
	}
	ApplyDamage(Damage, Source);
}

float UPTKHealthComponent::ApplyDamage(float Amount, AActor* DamageInstigator)
{
	// Already dead absorbs nothing. Without this, two hits landing on the same
	// frame would each see health at or below zero and each fire OnDeath.
	if (bDead || Amount <= 0.0f)
	{
		return 0.0f;
	}

	const float Applied = FMath::Min(Amount, CurrentHealth);
	CurrentHealth = FMath::Max(0.0f, CurrentHealth - Amount);

	OnHealthChanged.Broadcast(this, CurrentHealth, -Applied, DamageInstigator);

	UE_LOG(LogPTK, Verbose, TEXT("%s took %.0f damage from %s -> %.0f/%.0f"),
		*GetNameSafe(GetOwner()), Applied, *GetNameSafe(DamageInstigator),
		CurrentHealth, MaxHealth);

	if (CurrentHealth <= 0.0f)
	{
		bDead = true;
		UE_LOG(LogPTK, Log, TEXT("%s died (killer: %s)"),
			*GetNameSafe(GetOwner()), *GetNameSafe(DamageInstigator));
		OnDeath.Broadcast(this, DamageInstigator);
	}

	return Applied;
}

float UPTKHealthComponent::Heal(float Amount, AActor* Healer)
{
	if (bDead || Amount <= 0.0f)
	{
		return 0.0f;
	}

	const float Applied = FMath::Min(Amount, MaxHealth - CurrentHealth);
	if (Applied <= 0.0f)
	{
		return 0.0f;
	}

	CurrentHealth += Applied;
	OnHealthChanged.Broadcast(this, CurrentHealth, Applied, Healer);
	return Applied;
}

void UPTKHealthComponent::ResetHealth()
{
	CurrentHealth = MaxHealth;
	bDead = false;
	OnHealthChanged.Broadcast(this, CurrentHealth, MaxHealth, nullptr);
}

void UPTKHealthComponent::SetMaxHealth(float NewMax)
{
	MaxHealth = FMath::Max(1.0f, NewMax);
	CurrentHealth = MaxHealth;
	bDead = false;
}
